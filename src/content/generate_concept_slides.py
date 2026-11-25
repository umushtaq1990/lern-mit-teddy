"""Content pipeline: take hand-authored bilingual concept slides for each
lecture (src/content/concept_source/lecture-NN.json) and produce the final
lesson JSON + synchronized per-language audio the frontend serves.

Why hand-authored, not LLM-generated: the locally available Ollama models
(qwen2.5:3b -- fast but produced incoherent/wrong Urdu, including stray
Chinese characters on a plain translation task; gemma2:9b -- too slow on
CPU, 4+ minutes for a single sentence) were both tested directly against
this exact task and found unusable for authoring correctness-critical
teaching content. The local model is still the right choice for the live
Q&A feature (reactive, lower stakes, needs to be free at scale), but
curriculum content is written once and reused by every learner, so it gets
authored carefully instead. See concept_source/README.md for the schema.

Languages come from src/urdu_arabic/languages.py, the single registry also
used by tts.py, llm.py and the frontend's language picker -- this script
has no hardcoded language list.

Resumable per (lesson, part, language): a lecture already written to
OUTPUT_DIR is loaded back and merged, so only languages/parts missing from
it are synthesized. A killed or interrupted run, or a run after adding a
brand-new language to the registry, can simply be re-run -- already-done
work is never redone. Run standalone:

    uv run python -m src.content.generate_concept_slides

Output: one JSON file per lecture under OUTPUT_DIR, one MP3 per concept per
language under AUDIO_DIR, plus a manifest.json listing all lessons for the
frontend's lesson picker.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import edge_tts
from mutagen.mp3 import MP3

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.urdu_arabic.languages import DEFAULT_LANGUAGE, EXAMPLE_RATE, EXAMPLE_VOICE, LANGUAGES  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("generate_concept_slides.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("generate_concept_slides")

CONCEPT_SOURCE_DIR = REPO_ROOT / "src" / "content" / "concept_source"
OUTPUT_DIR = REPO_ROOT / "src" / "urdu_arabic" / "content_data"
AUDIO_DIR = OUTPUT_DIR / "audio"


def _load_sources() -> list[Path]:
    return sorted(CONCEPT_SOURCE_DIR.glob("lecture-*.json"))


def _lesson_id_for(path: Path) -> str:
    return path.stem  # files are already named lecture-NN.json


def _load_concepts(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["title"], data["concepts"]


async def _synthesize(text: str, voice: str, rate: str = "+0%") -> tuple[bytes, list[dict[str, float]]]:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio = bytearray()
    boundaries: list[dict[str, float]] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            boundaries.append(
                {
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                }
            )
    return bytes(audio), boundaries


# Urdu and Arabic share the same Unicode block, so "contains Arabic-range
# characters" alone can't tell a quoted Arabic term apart from a quoted
# Urdu phrase -- but Urdu has several letterforms Arabic doesn't use at all
# (distinct codepoints from their Arabic look-alikes: Urdu heh goal vs
# Arabic heh, Urdu yeh vs Arabic yeh, Urdu keheh vs Arabic kaf, retroflex
# consonants, noon ghunna, ...). The authoring convention is that a
# single-quoted span in an Urdu sentence is the Arabic term being taught,
# UNLESS it's actually Urdu prose -- so "contains Arabic/Urdu-range script
# but none of Urdu's own exclusive letters" is a reliable enough signal.
_ARABIC_RANGE = re.compile("[؀-ۿ]")
_URDU_SIGNATURE = re.compile("[ٹڈڑںےھگہیک]")
_QUOTED_SPAN = re.compile(r"'([^']*)'")


def _looks_arabic(span: str) -> bool:
    return bool(_ARABIC_RANGE.search(span)) and not _URDU_SIGNATURE.search(span)


# A fragment left over after splitting out quoted spans can be nothing but
# punctuation/whitespace (e.g. the trailing "۔" after a sentence ending
# right on a closing quote) -- that has nothing for a TTS engine to
# pronounce and Edge TTS raises NoAudioReceived on it, so these are
# filtered out before ever reaching _synthesize.
_NO_LETTERS = re.compile(r"^[\s.,;:!?۔؟،\-—()\[\]'\"“”’‘]*$")


def _is_speakable(text: str) -> bool:
    return not _NO_LETTERS.match(text)


def _split_segments(sentence: str) -> list[tuple[str, bool]]:
    """Split a sentence into (text, use_arabic_voice) runs. Only the
    single-quoted spans that look like genuine Arabic script (see
    `_looks_arabic`) are flagged for the dedicated Arabic voice -- quoted
    Urdu phrases, and English transliterations with internal apostrophes
    (e.g. "fa'il", "mu'annath"), are left alone."""
    parts = _QUOTED_SPAN.split(sentence)
    segments: list[tuple[str, bool]] = []
    for i, chunk in enumerate(parts):
        if not chunk or not _is_speakable(chunk):
            continue
        is_quoted = i % 2 == 1
        segments.append((chunk, is_quoted and _looks_arabic(chunk)))
    return segments


def _mp3_duration(data: bytes) -> float:
    return MP3(io.BytesIO(data)).info.length


async def _synthesize_mixed_sentence(sentence: str, main_voice: str) -> tuple[bytes, float]:
    """Synthesize one sentence as a sequence of per-segment TTS calls, each
    in whichever voice (main narration voice, or the dedicated Arabic voice)
    fits that segment, concatenated back together. Duration is measured
    from the actual audio rather than relying on Edge TTS's SentenceBoundary
    events, since those only apply within a single Communicate stream."""
    segments = _split_segments(sentence)
    if not segments:
        return b"", 0.0
    audio_chunks: list[bytes] = []
    total_duration = 0.0
    for text, is_arabic in segments:
        voice = EXAMPLE_VOICE if is_arabic else main_voice
        rate = EXAMPLE_RATE if is_arabic else "+0%"
        try:
            audio_bytes, _ = await _synthesize(text, voice, rate=rate)
        except Exception:
            logger.warning("segment synthesis failed, skipping just this segment: %r", text)
            continue
        if not audio_bytes:
            continue
        audio_chunks.append(audio_bytes)
        total_duration += _mp3_duration(audio_bytes)
    return b"".join(audio_chunks), total_duration


def _ensure_full_stop(sentence: str, language: str) -> str:
    """Edge TTS only emits a SentenceBoundary at real sentence punctuation --
    without a trailing sentence-final mark, two authored sentences joined by
    a space collapse into one TTS "sentence" and lose per-sentence timing,
    which breaks the pop-in/pop-out sync entirely."""
    s = sentence.strip()
    full_stop = LANGUAGES[language]["full_stop"]
    terminators = "۔؟!.?" if language != "ur" else "۔؟!"
    if s and s[-1] not in terminators:
        s += full_stop
    return s


def _is_legacy_part(part: dict[str, Any]) -> bool:
    return "title_urdu" in part


def _migrate_legacy_part(part: dict[str, Any]) -> dict[str, Any]:
    """A part written by the old Urdu-only pipeline -- reuse its existing
    audio/timings as the Urdu narration instead of re-synthesizing it."""
    return {
        "id": part["id"],
        "arabic_example": part.get("arabic_example"),
        "title": {"ur": part["title_urdu"]},
        "question": {"ur": part["question_urdu"]},
        "narration": {
            "ur": {"audio_url": part["audio_url"], "sentences": part["sentences"]},
        },
    }


async def _build_narration_mixed_voice(sentences: list[str], language: str) -> tuple[bytes, list[dict[str, float]]]:
    """Per-sentence synthesis with per-segment voice switching (see
    `_synthesize_mixed_sentence`), for languages where a quoted span can
    reliably be told apart as genuine Arabic script (today: Urdu only --
    see `_build_narration`). Boundaries are measured from the actual
    rendered audio instead of Edge TTS's SentenceBoundary events, since
    those don't apply across multiple concatenated Communicate streams."""
    main_voice = LANGUAGES[language]["voice"]
    audio_chunks: list[bytes] = []
    boundaries: list[dict[str, float]] = []
    cursor = 0.0
    for raw_sentence in sentences:
        sentence = _ensure_full_stop(raw_sentence, language)
        audio_bytes, duration = await _synthesize_mixed_sentence(sentence, main_voice)
        if not audio_bytes:
            continue
        audio_chunks.append(audio_bytes)
        boundaries.append({"text": raw_sentence, "start": cursor, "end": cursor + duration})
        cursor += duration
    return b"".join(audio_chunks), boundaries


def _build_narration(
    lesson_id: str, part_id: str, language: str, sentences: list[str]
) -> dict[str, Any]:
    if language == "ur":
        audio_bytes, boundaries = asyncio.run(_build_narration_mixed_voice(sentences, language))
    else:
        voice = LANGUAGES[language]["voice"]
        narration_text = " ".join(_ensure_full_stop(s, language) for s in sentences)
        audio_bytes, boundaries = asyncio.run(_synthesize(narration_text, voice))

    part_audio_dir = AUDIO_DIR / lesson_id
    part_audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = part_audio_dir / f"{part_id}-{language}.mp3"
    audio_path.write_bytes(audio_bytes)

    # Fallback timing (even spacing) if no boundaries came out of either path.
    if not boundaries:
        boundaries = [
            {"text": s, "start": i * 3.0, "end": (i + 1) * 3.0} for i, s in enumerate(sentences)
        ]

    return {
        "audio_url": f"/content/audio/{lesson_id}/{part_id}-{language}.mp3",
        "sentences": boundaries,
    }


def _build_example_audio(lesson_id: str, part_id: str, arabic_example: str) -> str:
    audio_bytes, _ = asyncio.run(_synthesize(arabic_example, EXAMPLE_VOICE, rate=EXAMPLE_RATE))
    part_audio_dir = AUDIO_DIR / lesson_id
    part_audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = part_audio_dir / f"{part_id}-example.mp3"
    audio_path.write_bytes(audio_bytes)
    return f"/content/audio/{lesson_id}/{part_id}-example.mp3"


def _build_example_entry_audio(lesson_id: str, part_id: str, example_id: str, arabic_text: str) -> str:
    audio_bytes, _ = asyncio.run(_synthesize(arabic_text, EXAMPLE_VOICE, rate=EXAMPLE_RATE))
    part_audio_dir = AUDIO_DIR / lesson_id
    part_audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = part_audio_dir / f"{part_id}-{example_id}.mp3"
    audio_path.write_bytes(audio_bytes)
    return f"/content/audio/{lesson_id}/{part_id}-{example_id}.mp3"


def _build_examples(
    lesson_id: str, part_id: str, source_examples: list[dict[str, Any]], existing_examples: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Each concept can carry several worked vocabulary/grammar examples
    (Arabic phrase + transliteration + per-language translation), each with
    its own slow-paced Arabic audio clip and its own picture (the picture is
    filled in later by generate_concept_images.py, not here). Resumable per
    example id, same pattern as the rest of this pipeline."""
    existing_by_id = {e["id"]: e for e in existing_examples}
    built = []
    for example in source_examples:
        example_id = example["id"]
        current = dict(existing_by_id.get(example_id, {}))
        current["id"] = example_id
        current["arabic"] = example["arabic"]
        current["transliteration"] = example.get("transliteration")
        current["translation"] = example.get("translation", {})
        current["rule"] = example.get("rule", {})
        if not current.get("audio_url"):
            try:
                current["audio_url"] = _build_example_entry_audio(
                    lesson_id, part_id, example_id, example["arabic"]
                )
                logger.info("%s/%s: synthesized example audio for %s", lesson_id, part_id, example_id)
            except Exception:
                current["audio_url"] = None
                logger.exception(
                    "%s/%s: failed to synthesize example audio for %s", lesson_id, part_id, example_id
                )
        current.setdefault("image_url", None)
        built.append(current)
    return built


def _build_part(
    lesson_id: str, part_index: int, concept: dict[str, Any], existing: dict[str, Any] | None
) -> dict[str, Any]:
    part_id = f"part-{part_index + 1}"

    if existing is not None and _is_legacy_part(existing):
        part = _migrate_legacy_part(existing)
    elif existing is not None:
        part = existing
    else:
        part = {
            "id": part_id,
            "arabic_example": concept.get("arabic_example"),
            "title": {},
            "question": {},
            "narration": {},
        }

    if part.get("arabic_example") and "example_audio_url" not in part:
        try:
            part["example_audio_url"] = _build_example_audio(lesson_id, part_id, part["arabic_example"])
            logger.info("%s/%s: synthesized Arabic example audio", lesson_id, part_id)
        except Exception:
            # Permanent, not retried forever -- some "examples" are bare
            # diacritic marks (e.g. tanween shapes) with nothing a TTS
            # engine can pronounce, not a transient failure.
            part["example_audio_url"] = None
            logger.exception("%s/%s: failed to synthesize example audio, leaving it unset", lesson_id, part_id)

    source_examples = concept.get("examples")
    if source_examples:
        part["examples"] = _build_examples(lesson_id, part_id, source_examples, part.get("examples", []))

    # Plain passthrough data (not generated/synthesized) -- an optional
    # alternate slide template, e.g. a two-column "A vs B" comparison table
    # for concepts that are fundamentally a contrast rather than a narrated
    # sequence. Re-synced from concept_source every run since it's cheap.
    if concept.get("layout"):
        part["layout"] = concept["layout"]
    if concept.get("comparison"):
        part["comparison"] = concept["comparison"]

    for language in LANGUAGES:
        if language in part["narration"]:
            continue  # already synthesized for this language -- don't redo it
        sentence_dicts = concept["sentences"]
        sentences_for_lang = [s.get(language, s.get(DEFAULT_LANGUAGE)) for s in sentence_dicts]
        if any(s is None for s in sentences_for_lang):
            logger.warning(
                "%s/%s: missing '%s' sentences in concept_source, skipping that language",
                lesson_id, part_id, language,
            )
            continue
        part["narration"][language] = _build_narration(lesson_id, part_id, language, sentences_for_lang)
        part["title"][language] = concept["title"].get(language, concept["title"].get(DEFAULT_LANGUAGE))
        part["question"][language] = concept["question"].get(language, concept["question"].get(DEFAULT_LANGUAGE))
        logger.info("%s/%s: synthesized narration for '%s'", lesson_id, part_id, language)

    return part


def _load_existing_lesson(out_path: Path) -> dict[str, Any] | None:
    if not out_path.exists():
        return None
    return json.loads(out_path.read_text(encoding="utf-8"))


def _needs_work(lesson: dict[str, Any] | None, concepts: list[dict[str, Any]]) -> bool:
    if lesson is None:
        return True
    if len(lesson.get("parts", [])) < len(concepts):
        return True
    for part, concept in zip(lesson["parts"], concepts):
        if _is_legacy_part(part) or set(LANGUAGES) - set(part.get("narration", {})):
            return True
        if part.get("arabic_example") and "example_audio_url" not in part:
            return True
        existing_examples = {e["id"]: e for e in part.get("examples", [])}
        for example in concept.get("examples", []):
            existing = existing_examples.get(example["id"])
            if existing is None or not existing.get("audio_url"):
                return True
        if concept.get("layout") and part.get("layout") != concept.get("layout"):
            return True
        if concept.get("comparison") and part.get("comparison") != concept.get("comparison"):
            return True
    return False


def _process_lecture(path: Path) -> None:
    lesson_id = _lesson_id_for(path)
    out_path = OUTPUT_DIR / f"{lesson_id}.json"

    title, concepts = _load_concepts(path)
    existing_lesson = _load_existing_lesson(out_path)

    if not _needs_work(existing_lesson, concepts):
        logger.info("Skipping %s (already complete for all languages)", lesson_id)
        return

    logger.info("Processing %s (%s)", lesson_id, path.name)
    existing_parts = {p["id"]: p for p in (existing_lesson or {}).get("parts", [])}

    parts = []
    for i, concept in enumerate(concepts):
        part_id = f"part-{i + 1}"
        try:
            parts.append(_build_part(lesson_id, i, concept, existing_parts.get(part_id)))
        except Exception:
            logger.exception("%s: failed to build part %d, skipping it", lesson_id, i + 1)
            if part_id in existing_parts:
                parts.append(existing_parts[part_id])  # keep whatever we already had

    if not parts:
        logger.error("%s: zero parts built, NOT writing a lesson file (will retry next run)", lesson_id)
        return

    lesson_title = {lang: title.get(lang, title.get(DEFAULT_LANGUAGE)) for lang in LANGUAGES}
    lesson = {"id": lesson_id, "title": lesson_title, "parts": parts}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("%s: wrote %s (%d parts)", lesson_id, out_path.name, len(parts))


def _write_manifest() -> None:
    lessons = []
    for p in sorted(OUTPUT_DIR.glob("lecture-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        lessons.append({"id": data["id"], "title": data["title"], "parts": len(data["parts"])})
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps({"lessons": lessons}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Wrote manifest with %d lessons", len(lessons))


def main() -> None:
    start = time.monotonic()
    paths = _load_sources()
    logger.info("Found %d authored lecture sources, languages=%s", len(paths), list(LANGUAGES))
    for path in paths:
        try:
            _process_lecture(path)
        except Exception:
            logger.exception("Unhandled error processing %s, continuing with next lecture", path.name)
        _write_manifest()  # refresh after every lecture so progress is visible early
    logger.info("Done in %.1fs", time.monotonic() - start)


if __name__ == "__main__":
    main()
