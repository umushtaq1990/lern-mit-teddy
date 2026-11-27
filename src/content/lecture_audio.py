"""Extracts real lecturer audio (and its matching Whisper transcript
segments) from the recorded classes in data/Arabic_Course/, for building
slides around actual lecture content instead of synthesized narration.

Usage (from generate_concept_slides.py or an ad-hoc script):

    transcript = load_transcript(1)                     # Class 1
    segments = segments_in_range(transcript, 220, 435)  # 3:40-7:15, clip-relative timing
    extract_audio_clip(transcript["source_path"], 220, 435, out_path)
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import static_ffmpeg

static_ffmpeg.add_paths()
import shutil  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COURSE_DIR = REPO_ROOT / "data" / "Arabic_Course"
TRANSCRIPTS_DIR = COURSE_DIR / "transcripts"


def _find_class_file(class_number: int, directory: Path, suffix: str) -> Path:
    pattern = re.compile(rf"Class {class_number}\.{suffix}$", re.IGNORECASE)
    matches = [p for p in directory.glob(f"*.{suffix}") if pattern.search(p.name)]
    if not matches:
        raise FileNotFoundError(f"No Class {class_number} .{suffix} file found in {directory}")
    if len(matches) > 1:
        raise FileNotFoundError(f"Ambiguous Class {class_number} match in {directory}: {matches}")
    return matches[0]


def load_transcript(class_number: int) -> dict[str, Any]:
    """Loads the Whisper transcript JSON for a class and resolves the
    matching source video path (so callers don't have to juggle both)."""
    transcript_path = _find_class_file(class_number, TRANSCRIPTS_DIR, "json")
    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    data["source_path"] = str(_find_class_file(class_number, COURSE_DIR, "mp4"))
    return data


def segments_in_range(transcript: dict[str, Any], start: float, end: float) -> list[dict[str, Any]]:
    """Whisper segments overlapping [start, end] (absolute seconds into the
    full class), with start/end re-timed to be relative to `start` -- i.e.
    relative to the extracted clip, matching how the frontend expects
    narration.sentences timing to work."""
    out = []
    for seg in transcript["segments"]:
        if seg["end"] <= start or seg["start"] >= end:
            continue
        out.append(
            {
                "text": seg["text"].strip(),
                "start": round(max(seg["start"], start) - start, 2),
                "end": round(min(seg["end"], end) - start, 2),
            }
        )
    return out


def extract_audio_clip(source_video: str, start: float, end: float, out_path: Path) -> None:
    """Extracts [start, end] (seconds) from source_video as an MP3, audio
    only (-vn), re-encoded (not stream-copied, since cut points rarely land
    on a keyframe/audio-frame boundary cleanly otherwise)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH (static_ffmpeg.add_paths() should have added it)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = end - start
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-i",
        source_video,
        "-t",
        str(duration),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "24000",
        "-ac",
        "1",
        "-q:a",
        "4",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")
