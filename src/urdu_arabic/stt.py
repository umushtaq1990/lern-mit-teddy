"""Speech-to-text, isolated from src.livekit.stt.faster_whisper_stt's
LiveKit-typed wrapper. Same underlying faster-whisper library, called
directly on a saved audio file path -- no AudioFrame/rtc types needed.
"""

from __future__ import annotations

import logging
from typing import Any

from .languages import DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)

_whisper: Any = None  # lazy-loaded on first use, same as the LiveKit wrapper does


def _load_model(model_name: str = "small"):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel  # noqa: PLC0415

        logger.info("Loading faster-whisper model '%s' for Urdu/Arabic app...", model_name)
        _whisper = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _whisper


def transcribe(audio_path: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe an audio file on disk. Returns the transcript text (possibly empty)."""
    model = _load_model()
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=False,
        no_speech_threshold=0.3,
        condition_on_previous_text=False,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    logger.info(
        "Transcribed %s -> %r (lang=%s, prob=%.2f)",
        audio_path, text, info.language, info.language_probability,
    )
    return text
