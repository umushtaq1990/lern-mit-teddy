"""Single source of truth for which languages this app supports.

Every other module (tts.py's voice selection, the content pipeline, the
Q&A system prompt, and the frontend's language picker via GET /api/languages)
reads from this registry instead of keeping its own hardcoded list. Adding a
third language later means one new entry here plus translated content --
no code changes anywhere else.
"""

from __future__ import annotations

LANGUAGES: dict[str, dict[str, str]] = {
    "ur": {
        "label": "اردو",
        "dir": "rtl",
        "voice": "ur-PK-UzmaNeural",
        "stt_code": "ur",
        "full_stop": "۔",
        "prompt_name": "Urdu",
    },
    "en": {
        "label": "English",
        "dir": "ltr",
        "voice": "en-US-JennyNeural",
        "stt_code": "en",
        "full_stop": ".",
        "prompt_name": "English",
    },
}

DEFAULT_LANGUAGE = "ur"


def is_supported(language: str) -> bool:
    return language in LANGUAGES
