"""Prompt loader — picks the target-language prompt file and fills in native language name."""

from __future__ import annotations

from . import ar, de, en, hi

# Each module exports PROMPT (str with {native_language} placeholder) and
# NATIVE_LANGUAGE_NAMES (dict[lang_code -> name in target language]).
_LANG_MODULES = {
    "de": de,
    "en": en,
    "hi": hi,
    "ar": ar,
}

# Fallback native-language names in English (used when a language module doesn't cover the code)
_FALLBACK_NATIVE_NAMES: dict[str, str] = {
    "en": "English", "de": "German", "hi": "Hindi", "ur": "Urdu", "ar": "Arabic",
    "es": "Spanish", "fr": "French", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "pt": "Portuguese", "it": "Italian",
    "nl": "Dutch", "ru": "Russian", "tr": "Turkish",
}


def _native_name(mod, native_lang_code: str) -> str:
    return mod.NATIVE_LANGUAGE_NAMES.get(
        native_lang_code,
        _FALLBACK_NATIVE_NAMES.get(native_lang_code, "English"),
    )


def build_prompt(lang_code: str, native_lang_code: str) -> str:
    """Return the full system prompt for the given target language.

    Falls back to English if no dedicated prompt file exists for lang_code.
    """
    mod = _LANG_MODULES.get(lang_code, _LANG_MODULES["en"])
    return mod.PROMPT.format(native_language=_native_name(mod, native_lang_code))


def build_conversation_helper_prompt(lang_code: str, native_lang_code: str) -> str:
    """Return the Conversation Helper system prompt (phrase-lookup coach mode,
    not vocab-card drilling). Falls back to the regular persona prompt for any
    language module that doesn't define a dedicated one."""
    mod = _LANG_MODULES.get(lang_code, _LANG_MODULES["en"])
    template = getattr(mod, "CONVERSATION_HELPER_PROMPT", None) or mod.PROMPT
    return template.format(native_language=_native_name(mod, native_lang_code))
