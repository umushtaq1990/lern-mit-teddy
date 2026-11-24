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
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import edge_tts

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.urdu_arabic.languages import DEFAULT_LANGUAGE, LANGUAGES  # noqa: E402

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


async def _synthesize(text: str, voice: str) -> tuple[bytes, list[dict[str, float]]]:
    communicate = edge_tts.Communicate(text, voice)
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


def _build_narration(
    lesson_id: str, part_id: str, language: str, sentences: list[str]
) -> dict[str, Any]:
    voice = LANGUAGES[language]["voice"]
    narration_text = " ".join(_ensure_full_stop(s, language) for s in sentences)
    audio_bytes, boundaries = asyncio.run(_synthesize(narration_text, voice))

    part_audio_dir = AUDIO_DIR / lesson_id
    part_audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = part_audio_dir / f"{part_id}-{language}.mp3"
    audio_path.write_bytes(audio_bytes)

    # Fallback timing (even spacing) if Edge TTS gave no boundaries for this voice/text.
    if not boundaries:
        boundaries = [
            {"text": s, "start": i * 3.0, "end": (i + 1) * 3.0} for i, s in enumerate(sentences)
        ]

    return {
        "audio_url": f"/content/audio/{lesson_id}/{part_id}-{language}.mp3",
        "sentences": boundaries,
    }


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


def _needs_work(lesson: dict[str, Any] | None, concept_count: int) -> bool:
    if lesson is None:
        return True
    if len(lesson.get("parts", [])) < concept_count:
        return True
    for part in lesson["parts"]:
        if _is_legacy_part(part) or set(LANGUAGES) - set(part.get("narration", {})):
            return True
    return False


def _process_lecture(path: Path) -> None:
    lesson_id = _lesson_id_for(path)
    out_path = OUTPUT_DIR / f"{lesson_id}.json"

    title, concepts = _load_concepts(path)
    existing_lesson = _load_existing_lesson(out_path)

    if not _needs_work(existing_lesson, len(concepts)):
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
