"""Standalone batch job: transcribe Arabic course lecture recordings in data/
and summarize what each one covers, to prep for later ingestion into the app
(see the `content_items` table in src/db/models.py). Not part of the live
request path — run manually:

    uv run python -m src.content.transcribe_lectures --limit 1

Outputs land next to the source videos under data/<course>/transcripts/ and
data/<course>/summaries/ (data/ is gitignored, so these stay local).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# faster-whisper's CUDA backend (ctranslate2) needs cuBLAS/cuDNN DLLs that
# aren't pip-installable on Windows (no win_amd64 wheels for
# nvidia-cublas-cu12/nvidia-cudnn-cu12). Reuse the ones bundled with a local
# CUDA-enabled torch install instead of requiring a system CUDA toolkit.
_TORCH_CUDA_LIB_DIR = (
    r"C:\Users\usman\AppData\Local\Programs\Python\Python310\Lib\site-packages\torch\lib"
)
if os.path.isdir(_TORCH_CUDA_LIB_DIR):
    os.environ["PATH"] = _TORCH_CUDA_LIB_DIR + os.pathsep + os.environ.get("PATH", "")

import gc  # noqa: E402

import av  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

AUDIO_SAMPLE_RATE = 16000

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".m4a", ".mp3", ".wav"}

SUMMARY_SYSTEM_PROMPT = """You are helping build an Arabic-learning app from a
beginner/intermediate Arabic course's lecture transcripts. The instructor
teaches Arabic grammar and vocabulary while explaining in Urdu, with
occasional English asides (e.g. logistics, homework, timers). The transcript
you receive is therefore a genuine mix of Arabic, Urdu, and English in one
stream of speech-to-text output — this is expected, not an error.

Given the raw transcript of one lecture, write a concise study summary IN
ENGLISH ONLY, so a course maintainer can quickly see what a lecture covers
without rewatching it.

You MUST always reply using exactly this Markdown structure, with no
preamble, no clarifying questions, and no meta-commentary about the input:

## Topics Covered
Bullet list of the grammar/vocabulary/conversation topics taught in this
lecture.
## Key Vocabulary
Bullet list of new Arabic words/phrases introduced, each as
"arabic_word — transliteration — English meaning".
## Grammar Points
Bullet list of any grammar rules explained (e.g. verb conjugation, pronouns,
sentence structure).
## Notes
Anything else worth flagging (recording quality issues, off-topic sections,
homework/assignments mentioned, logistics discussed in Urdu/English).

Be faithful to the transcript; do not invent content it doesn't contain. If
a section has nothing to report, write "None noted in this transcript."
under that heading instead of omitting the heading or asking for
clarification.
"""


def iter_lecture_files(data_dir: Path) -> list[Path]:
    files = [p for p in sorted(data_dir.rglob("*")) if p.suffix.lower() in VIDEO_EXTENSIONS]
    return files


def iter_audio_chunks(video_path: str, chunk_seconds: int):
    """Decode audio from `video_path` and yield fixed-size float32 mono PCM
    chunks at AUDIO_SAMPLE_RATE, never holding more than one chunk's worth of
    decoded samples in memory at a time.

    faster-whisper's own `decode_audio` buffers the ENTIRE file's decoded PCM
    in memory before returning — for a ~90min lecture that's a 350MB+ array,
    which reliably OOMs this machine when free RAM dips below ~500MB (shared
    with other local projects' containers). Streaming the resample output
    straight into bounded chunks keeps memory flat regardless of file length.
    """
    chunk_samples = chunk_seconds * AUDIO_SAMPLE_RATE
    bytes_per_sample = 2  # s16
    chunk_bytes = chunk_samples * bytes_per_sample
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=AUDIO_SAMPLE_RATE)
    buffer = bytearray()

    def _drain(require_full_chunk: bool):
        while len(buffer) >= (chunk_bytes if require_full_chunk else 1):
            take = min(len(buffer), chunk_bytes)
            raw = bytes(buffer[:take])
            del buffer[:take]
            pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            yield pcm
            if not require_full_chunk:
                return

    with av.open(video_path, mode="r", metadata_errors="ignore") as container:
        for frame in container.decode(audio=0):
            for rframe in resampler.resample(frame):
                buffer += rframe.to_ndarray().tobytes()
                yield from _drain(require_full_chunk=True)
        for rframe in resampler.resample(None):  # flush resampler
            buffer += rframe.to_ndarray().tobytes()
            yield from _drain(require_full_chunk=True)

    if buffer:
        yield from _drain(require_full_chunk=False)

    del resampler
    gc.collect()


def transcribe(
    model: WhisperModel, video_path: Path, out_dir: Path, language: str, chunk_seconds: int = 30
) -> tuple[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / f"{video_path.stem}.txt"
    json_path = out_dir / f"{video_path.stem}.json"

    full_text_parts: list[str] = []
    segment_records: list[dict] = []
    detected_language = language
    t_start = time.time()
    audio_pos = 0.0

    for chunk in iter_audio_chunks(str(video_path), chunk_seconds):
        offset = audio_pos
        segments, info = model.transcribe(
            chunk,
            language=language,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        detected_language = info.language or detected_language
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            full_text_parts.append(text)
            segment_records.append(
                {"start": round(offset + seg.start, 2), "end": round(offset + seg.end, 2), "text": text}
            )

        audio_pos += len(chunk) / AUDIO_SAMPLE_RATE
        elapsed = time.time() - t_start
        print(
            f"    ...audio_pos={audio_pos:.0f}s wall_elapsed={elapsed:.0f}s "
            f"rtf={elapsed / max(audio_pos, 1):.2f}",
            flush=True,
        )

    duration_seconds = audio_pos
    full_text = "\n".join(full_text_parts)
    txt_path.write_text(full_text, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "source": video_path.name,
                "language": detected_language,
                "duration_seconds": round(duration_seconds, 1),
                "segments": segment_records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return full_text, txt_path


def summarize(
    ollama_base_url: str, model: str, lecture_title: str, transcript_text: str, out_dir: Path
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{Path(lecture_title).stem}.md"

    if not transcript_text.strip():
        md_path.write_text(
            f"# {lecture_title}\n\nTranscript was empty — nothing to summarize.\n",
            encoding="utf-8",
        )
        return md_path

    # Keep the prompt within num_ctx=32768 tokens for very long lectures —
    # Arabic/Urdu script runs ~2-3 chars/token, so this stays well under
    # budget alongside the system prompt. Truncating loses only the tail of
    # the longest recordings; good enough for an overnight first pass.
    max_chars = 70_000
    if len(transcript_text) > max_chars:
        transcript_text = transcript_text[:max_chars] + "\n[...transcript truncated for length...]"

    # Ollama's native /api/chat (not the OpenAI-compat /v1 endpoint) is used
    # here because it exposes `think: false` — qwen3.5 is a "thinking" model
    # whose real answer lands in a hidden reasoning channel on the OpenAI
    # route, often leaving `content` empty once the token budget is spent on
    # the hidden reasoning before it gets to the final answer.
    response = requests.post(
        f"{ollama_base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Lecture: {lecture_title}\n\nTranscript:\n{transcript_text}",
                },
            ],
            "think": False,
            "stream": False,
            "options": {"num_ctx": 32768},
        },
        timeout=600,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]
    md_path.write_text(f"# {lecture_title}\n\n{content}\n", encoding="utf-8")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Root folder to scan for lecture files")
    parser.add_argument("--language", default="ar", help="faster-whisper language code")
    parser.add_argument(
        "--model-size",
        default="large-v3-turbo",
        help="faster-whisper model size (tiny/base/small/medium/large-v3/large-v3-turbo)",
    )
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--cpu-threads", type=int, default=16)
    parser.add_argument(
        "--summary-model", default="qwen3.5:9b", help="Ollama model tag used for summaries"
    )
    parser.add_argument(
        "--summary-base-url",
        default="http://127.0.0.1:11500",
        help=(
            "Ollama server base URL (no /v1 suffix — native API is used for "
            "think:false support). Default is a native Windows Ollama "
            "instance on a non-default port, kept separate from the "
            "Docker-based Ollama container other local projects may run on "
            "the standard port 11434."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N files (for testing)")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--force", action="store_true", help="Reprocess even if outputs already exist")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    files = iter_lecture_files(data_dir)
    if args.limit:
        files = files[: args.limit]

    print(f"Found {len(files)} lecture file(s) under {data_dir}")

    # Phase 1: transcription only. Run to completion and release the whisper
    # model (and its CUDA context) before starting any Ollama calls — the
    # two were competing for the same 8GB of VRAM when interleaved per-file,
    # which caused intermittent CUDA OOM once Ollama's keep_alive kept its
    # model resident between calls.
    whisper_model = WhisperModel(
        args.model_size,
        device=args.device,
        compute_type=args.compute_type,
        cpu_threads=args.cpu_threads if args.device == "cpu" else 0,
    )

    for i, video_path in enumerate(files, start=1):
        course_dir = video_path.parent
        transcripts_dir = course_dir / "transcripts"
        txt_path = transcripts_dir / f"{video_path.stem}.txt"

        if not args.force and txt_path.exists():
            print(f"[{i}/{len(files)}] transcript exists, skip: {video_path.name}")
            continue

        for attempt in range(1, 3):
            try:
                print(f"[{i}/{len(files)}] transcribing (attempt {attempt}): {video_path.name}")
                t0 = time.time()
                transcript_text, _ = transcribe(
                    whisper_model, video_path, transcripts_dir, args.language
                )
                print(f"    transcribed in {time.time() - t0:.1f}s ({len(transcript_text)} chars)")
                break
            except Exception as exc:  # noqa: BLE001 — unattended batch: log, retry once, move on
                print(f"    FAILED on {video_path.name} (attempt {attempt}): {exc!r}")
                gc.collect()
                time.sleep(10)

    del whisper_model
    gc.collect()
    time.sleep(5)  # give the CUDA context time to actually release VRAM

    # Phase 2: summarization only, now that the GPU is free for Ollama.
    for i, video_path in enumerate(files, start=1):
        course_dir = video_path.parent
        transcripts_dir = course_dir / "transcripts"
        summaries_dir = course_dir / "summaries"
        txt_path = transcripts_dir / f"{video_path.stem}.txt"
        md_path = summaries_dir / f"{video_path.stem}.md"

        if not txt_path.exists():
            print(f"[{i}/{len(files)}] no transcript, skip summary: {video_path.name}")
            continue
        if not args.force and md_path.exists():
            print(f"[{i}/{len(files)}] summary exists, skip: {video_path.name}")
            continue

        transcript_text = txt_path.read_text(encoding="utf-8")
        for attempt in range(1, 3):
            try:
                print(f"[{i}/{len(files)}] summarizing (attempt {attempt}): {video_path.name}")
                t0 = time.time()
                summarize(
                    args.summary_base_url,
                    args.summary_model,
                    video_path.name,
                    transcript_text,
                    summaries_dir,
                )
                print(f"    summarized in {time.time() - t0:.1f}s")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"    FAILED summarizing {video_path.name} (attempt {attempt}): {exc!r}")
                time.sleep(10)

    print("Done.")


if __name__ == "__main__":
    main()
