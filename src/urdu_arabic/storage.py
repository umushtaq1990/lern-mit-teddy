"""Local-disk storage for uploaded/generated audio files.

Isolated behind this one module so swapping to real blob storage later
(nothing else in this repo does blob storage yet either) only touches
this file.
"""

from __future__ import annotations

import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "urdu_arabic_answers"


def save_bytes(data: bytes, subdir: str, suffix: str = ".bin") -> str:
    """Save bytes under DATA_DIR/subdir/<random>.<suffix>, return the path as a string."""
    target_dir = DATA_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path)


def read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()
