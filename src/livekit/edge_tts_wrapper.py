"""Microsoft Edge TTS — native neural voices for all four LinguaAI languages.

Uses the `edge-tts` package which calls Microsoft's free Speech service.
Produces MP3 audio at 24 kHz that LiveKit decodes natively.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import edge_tts

from livekit.agents import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS
from livekit.agents import tts as tts_base
from livekit.agents.tts import AudioEmitter

logger = logging.getLogger(__name__)

# Native Edge TTS voices per language — multilingual variants preferred for
# German and English because they handle code-switching (e.g. German teacher
# giving an English translation) more naturally.
EDGE_TTS_VOICES: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "de": "de-DE-SeraphinaMultilingualNeural",
    "hi": "hi-IN-SwaraNeural",
    "ar": "ar-SA-ZariyahNeural",
}

_SAMPLE_RATE = 24000
_NUM_CHANNELS = 1


class EdgeTTSProvider(tts_base.TTS):
    """LiveKit TTS adapter backed by Microsoft Edge TTS neural voices."""

    def __init__(self, *, language: str = "en", rate: str = "+0%") -> None:
        super().__init__(
            capabilities=tts_base.TTSCapabilities(streaming=False),
            sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS,
        )
        self._voice = EDGE_TTS_VOICES.get(language, EDGE_TTS_VOICES["en"])
        self._rate = rate
        logger.info("EdgeTTS init — language=%s voice=%s rate=%s", language, self._voice, rate)

    @property
    def model(self) -> str:
        return "edge-tts"

    @property
    def provider(self) -> str:
        return "microsoft-edge"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "EdgeChunkedStream":
        return EdgeChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class EdgeChunkedStream(tts_base.ChunkedStream):
    def __init__(
        self,
        *,
        tts: EdgeTTSProvider,
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._provider = tts

    async def _run(self, output_emitter: AudioEmitter) -> None:
        communicate = edge_tts.Communicate(
            self._input_text, self._provider._voice, rate=self._provider._rate
        )

        initialized = False
        got_audio = False
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                if not initialized:
                    output_emitter.initialize(
                        request_id=str(uuid.uuid4()),
                        sample_rate=_SAMPLE_RATE,
                        num_channels=_NUM_CHANNELS,
                        mime_type="audio/mpeg",
                    )
                    initialized = True
                output_emitter.push(chunk["data"])
                got_audio = True

        if not got_audio:
            logger.warning("EdgeTTS returned no audio for text: %r", self._input_text[:80])
