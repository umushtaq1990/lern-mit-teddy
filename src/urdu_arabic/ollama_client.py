"""Thin HTTP client for a local Ollama server, mirroring the JME reference
architecture's app/extraction/ollama_client.py: plain httpx against Ollama's
native /api/generate endpoint (not the OpenAI-compatible /v1/... shape), so
this app uses a free, local, no-API-key Qwen model instead of OpenAI.
"""

from __future__ import annotations

import logging

import httpx

from src.settings import get_settings

logger = logging.getLogger(__name__)


def generate(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    timeout_seconds: int | None = None,
) -> str:
    """Single-turn generation. Blocking -- call from a worker thread/process."""
    settings = get_settings()
    payload = {
        "model": model or settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    with httpx.Client(timeout=timeout_seconds or settings.ollama_timeout_seconds) as client:
        resp = client.post(f"{settings.ollama_url}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()

    text = data.get("response", "").strip()
    if not text:
        logger.warning("Ollama returned an empty response for prompt: %r", prompt[:80])
    return text
