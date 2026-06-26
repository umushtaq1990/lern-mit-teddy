"""NVIDIA Riva gRPC TTS — Magpie Chatterbox Multilingual model.

Uses nvidia-riva-client over gRPC to synthesize speech. The Riva service
function ID routes the request to the Magpie TTS model hosted on NVIDIA Cloud.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from livekit.agents import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS
from livekit.agents import tts as tts_base
from livekit.agents.tts import AudioEmitter

logger = logging.getLogger(__name__)

import os

_RIVA_SERVER = "grpc.nvcf.nvidia.com:443"
_FUNCTION_ID = os.getenv("NVIDIA_TTS_FUNCTION_ID", "ddacc747-1269-4fab-bfd9-8f593dead106")
_SAMPLE_RATE = 22050
_NUM_CHANNELS = 1

# BCP-47 code → (Riva language code, Chatterbox voice name)
LANGUAGE_VOICES: dict[str, tuple[str, str]] = {
    "en": ("en-US", "Chatterbox-Multilingual.en-US.Female"),
    "de": ("de-DE", "Chatterbox-Multilingual.de-DE.Female"),
    "hi": ("hi-IN", "Chatterbox-Multilingual.hi-IN.Female"),
    "ar": ("ar-AR", "Chatterbox-Multilingual.ar-AR.Female"),
}


class RivaTTS(tts_base.TTS):
    """NVIDIA Riva gRPC TTS backed by the Magpie Chatterbox Multilingual model."""

    def __init__(self, *, api_key: str, language: str = "en") -> None:
        super().__init__(
            capabilities=tts_base.TTSCapabilities(streaming=False),
            sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS,
        )
        self._api_key = api_key
        lang_info = LANGUAGE_VOICES.get(language, LANGUAGE_VOICES["en"])
        self._language_code, self._voice = lang_info
        logger.info(
            "RivaTTS initialised — voice=%s language_code=%s",
            self._voice, self._language_code,
        )

    @property
    def model(self) -> str:
        return "magpie-chatterbox-multilingual"

    @property
    def provider(self) -> str:
        return "nvidia-riva"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "RivaChunkedStream":
        return RivaChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class RivaChunkedStream(tts_base.ChunkedStream):
    """Single-shot synthesis via Riva gRPC; pushes raw PCM bytes to LiveKit."""

    def __init__(
        self,
        *,
        tts: RivaTTS,
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._riva_tts = tts

    async def _run(self, output_emitter: AudioEmitter) -> None:
        import riva.client  # nvidia-riva-client must be installed

        loop = asyncio.get_event_loop()

        def _call_riva() -> bytes:
            auth = riva.client.Auth(
                use_ssl=True,
                metadata_args=[
                    ["function-id", _FUNCTION_ID],
                    ["authorization", f"Bearer {self._riva_tts._api_key}"],
                ],
                uri=_RIVA_SERVER,
            )
            client = riva.client.SpeechSynthesisService(auth)
            response = client.synthesize(
                text=self._input_text,
                voice_name=self._riva_tts._voice,
                language_code=self._riva_tts._language_code,
                sample_rate_hz=_SAMPLE_RATE,
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
            )
            return response.audio

        audio_bytes: bytes = await loop.run_in_executor(None, _call_riva)

        output_emitter.initialize(
            request_id=str(uuid.uuid4()),
            sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS,
            mime_type=f"audio/pcm;rate={_SAMPLE_RATE}",
        )
        output_emitter.push(audio_bytes)
