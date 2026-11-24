"""Text-to-speech, isolated from src.livekit.edge_tts_wrapper's LiveKit TTS
adapter classes. Calls the edge-tts package directly and returns plain bytes.
"""

from __future__ import annotations

import asyncio
import logging

import edge_tts

from .languages import DEFAULT_LANGUAGE, LANGUAGES

logger = logging.getLogger(__name__)

VOICES: dict[str, str] = {code: meta["voice"] for code, meta in LANGUAGES.items()}


async def _synthesize_async(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.extend(chunk["data"])
    if not chunks:
        logger.warning("Edge TTS returned no audio for text: %r", text[:80])
    return bytes(chunks)


def synthesize(text: str, language: str = DEFAULT_LANGUAGE) -> bytes:
    """Synthesize `text` to MP3 bytes. Blocking — run in a worker thread/process."""
    voice = VOICES.get(language, VOICES[DEFAULT_LANGUAGE])
    return asyncio.run(_synthesize_async(text, voice))
