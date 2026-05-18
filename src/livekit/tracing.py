"""Langfuse tracing for the voice agent pipeline.

Creates one trace per voice session and exposes helpers for STT, LLM, and TTS
spans so every hop in the pipeline is visible in Langfuse.

Gracefully no-ops when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set,
so the agent still works in environments without tracing configured.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("voice-tracer")


class _NoopSpan:
    """Returned when Langfuse is disabled — every operation is a silent no-op."""

    def end(self, **kwargs) -> None:
        pass

    def update(self, **kwargs) -> None:
        pass


class VoiceSessionTracer:
    """One Langfuse trace that covers a complete voice session.

    Attach STT / LLM / TTS child spans via the helper methods.  The LangChain
    callback returned by ``get_langchain_handler()`` links LangGraph LLM calls
    to the same trace automatically.
    """

    def __init__(
        self,
        *,
        session_id: str,
        room: str,
        participant: str,
        thread_id: str | None,
        stt_model: str = "faster-whisper/base",
        llm_model: str = "gpt-4.1-nano",
        tts_model: str = "hume",
    ) -> None:
        self._enabled = False
        self._lf = None
        self.trace = None

        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")

        if not (pk and sk):
            logger.info("LANGFUSE_PUBLIC_KEY / SECRET not set — tracing disabled")
            return

        try:
            from langfuse import Langfuse  # noqa: PLC0415

            self._lf = Langfuse(
                public_key=pk,
                secret_key=sk,
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
            self.trace = self._lf.trace(
                name="voice-session",
                session_id=session_id,
                user_id=participant,
                metadata={
                    "room": room,
                    "participant": participant,
                    "thread_id": thread_id or "none",
                    "stt_model": stt_model,
                    "llm_model": llm_model,
                    "tts_model": tts_model,
                },
                tags=["voice-agent"],
            )
            self._enabled = True
            logger.info("Langfuse tracing enabled  session_id=%s", session_id)
        except Exception as exc:
            logger.warning("Langfuse init failed — tracing disabled: %s", exc)

    # ------------------------------------------------------------------
    # LangChain / LangGraph
    # ------------------------------------------------------------------

    def get_langchain_handler(self):
        """LangChain callback that links every LLM call to this session trace.

        Pass the returned handler in the LangGraph ``config["callbacks"]`` list.
        Returns None when tracing is disabled so callers can skip it safely.
        """
        if not self._enabled or self.trace is None:
            return None
        try:
            return self.trace.get_langchain_handler()
        except Exception as exc:
            logger.warning("get_langchain_handler failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # STT
    # ------------------------------------------------------------------

    def stt_span(
        self,
        *,
        audio_duration_s: float,
        model: str = "faster-whisper/base",
        language: str = "en",
    ):
        """Open an STT span.  Call ``.end(output={...})`` when transcription finishes."""
        if not self._enabled or self.trace is None:
            return _NoopSpan()
        try:
            return self.trace.span(
                name="stt",
                input={"audio_duration_seconds": round(audio_duration_s, 3)},
                metadata={"model": model, "language": language},
            )
        except Exception:
            return _NoopSpan()

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------

    def tts_span(self, *, text: str, model: str = "hume"):
        """Open a TTS span.  Call ``.end()`` when audio synthesis finishes."""
        if not self._enabled or self.trace is None:
            return _NoopSpan()
        try:
            return self.trace.span(
                name="tts",
                input={"text": text, "char_count": len(text)},
                metadata={"model": model},
            )
        except Exception:
            return _NoopSpan()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush buffered events to Langfuse.  Call this on session teardown."""
        if self._enabled and self._lf:
            try:
                self._lf.flush()
                logger.info("Langfuse events flushed")
            except Exception as exc:
                logger.warning("Langfuse flush error: %s", exc)
