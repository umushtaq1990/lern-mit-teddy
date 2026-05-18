"""Local STT using faster-whisper (open-source Whisper via CTranslate2).

Implements the livekit-agents STT interface so it can be used as a drop-in
replacement for cloud-based STT plugins in the AgentSession pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import numpy as np
from livekit import rtc
from livekit.agents import stt
from livekit.agents.stt import SpeechData, SpeechEvent, SpeechEventType
from livekit.agents.types import (
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    NotGivenOr,
)

if TYPE_CHECKING:
    from ..tracing import VoiceSessionTracer

logger = logging.getLogger("faster-whisper-stt")

WHISPER_SAMPLE_RATE = 16_000  # Whisper always expects 16 kHz mono float32


def _frames_to_float32(frames: list[rtc.AudioFrame]) -> tuple[np.ndarray, int]:
    """Concatenate LiveKit AudioFrames into a mono float32 array.

    Returns (audio_array, sample_rate).
    """
    if not frames:
        return np.array([], dtype=np.float32), WHISPER_SAMPLE_RATE

    sample_rate = frames[0].sample_rate
    num_channels = frames[0].num_channels
    chunks: list[np.ndarray] = []

    for frame in frames:
        arr = np.frombuffer(bytes(frame.data), dtype=np.int16).astype(np.float32) / 32768.0
        if num_channels > 1:
            arr = arr.reshape(-1, num_channels).mean(axis=1)
        chunks.append(arr)

    return np.concatenate(chunks), sample_rate


class FasterWhisperSTT(stt.STT):
    """Open-source STT backed by faster-whisper running entirely on-device."""

    def __init__(
        self,
        *,
        model: str = "base",
        language: str = "en",
        device: str = "cpu",
        compute_type: str = "int8",
        tracer: VoiceSessionTracer | None = None,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=False)
        )
        self._model_name = model
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._tracer = tracer
        self._whisper: Any = None  # lazy-loaded on first use

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel  # noqa: PLC0415

            logger.info(
                "Loading faster-whisper model '%s' on %s (%s) …",
                self._model_name,
                self._device,
                self._compute_type,
            )
            self._whisper = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("faster-whisper model ready")
        return self._whisper

    def _transcribe_sync(self, audio: np.ndarray, language: str) -> SpeechEvent:
        """Blocking transcription — must be called inside run_in_executor."""
        model = self._load_model()

        if len(audio) == 0:
            return SpeechEvent(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[SpeechData(text="", language=language, confidence=0.0)],
            )

        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=False,  # VAD is handled upstream by Silero
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.debug("Transcription: %r (lang=%s, prob=%.2f)", text, info.language, info.language_probability)

        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                SpeechData(
                    text=text,
                    language=info.language,
                    confidence=info.language_probability,
                )
            ],
        )

    async def _transcribe_frames(self, frames: list[rtc.AudioFrame], language: str) -> SpeechEvent:
        """Convert frames to float32, run faster-whisper, emit a Langfuse STT span."""
        audio, sr = _frames_to_float32(frames)

        # Frames arriving here are already at WHISPER_SAMPLE_RATE because
        # RecognizeStream resamples them when sample_rate is set.
        duration_s = len(audio) / WHISPER_SAMPLE_RATE

        span = (
            self._tracer.stt_span(
                audio_duration_s=duration_s,
                model=f"faster-whisper/{self._model_name}",
                language=language,
            )
            if self._tracer
            else None
        )

        loop = asyncio.get_event_loop()
        event = await loop.run_in_executor(None, self._transcribe_sync, audio, language)

        if span is not None:
            alt = event.alternatives[0] if event.alternatives else None
            span.end(
                output={
                    "text": alt.text if alt else "",
                    "detected_language": alt.language if alt else "",
                    "confidence": round(alt.confidence, 3) if alt else 0.0,
                }
            )

        return event

    # ------------------------------------------------------------------
    # livekit-agents STT interface
    # ------------------------------------------------------------------

    async def _recognize_impl(
        self,
        buffer: Any,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> SpeechEvent:
        frames = buffer if isinstance(buffer, list) else [buffer]
        lang = language if language is not NOT_GIVEN else self._language
        return await self._transcribe_frames(frames, lang)

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "FasterWhisperStream":
        lang = language if language is not NOT_GIVEN else self._language
        return FasterWhisperStream(
            stt=self,
            language=lang,
            conn_options=conn_options,
        )


class FasterWhisperStream(stt.RecognizeStream):
    """Buffering speech stream for faster-whisper.

    Collects audio frames until a flush sentinel signals end-of-speech,
    then runs the (blocking) transcription in a thread pool executor.

    RecognizeStream automatically resamples incoming audio to WHISPER_SAMPLE_RATE
    so no manual resampling is needed inside _run.
    """

    def __init__(
        self,
        *,
        stt: FasterWhisperSTT,
        language: str,
        conn_options: APIConnectOptions,
    ) -> None:
        # Pass sample_rate so RecognizeStream resamples frames to 16 kHz automatically
        super().__init__(stt=stt, conn_options=conn_options, sample_rate=WHISPER_SAMPLE_RATE)
        self._stt_ref = stt
        self._language = language

    async def _run(self) -> None:
        frames: list[rtc.AudioFrame] = []

        async for data in self._input_ch:
            if isinstance(data, self._FlushSentinel):
                if frames:
                    event = await self._stt_ref._transcribe_frames(frames, self._language)
                    if event.alternatives and event.alternatives[0].text:
                        self._event_ch.send_nowait(event)
                    frames.clear()
            else:
                frames.append(data)
