"""Pure-logic tests for the prompt loader — no LLM, no network, no env vars."""

from __future__ import annotations

from src.langgraph.prompts import build_conversation_helper_prompt, build_prompt


def test_build_prompt_fills_native_language():
    # The German prompt module names the native language in German ("Englisch"),
    # not in English — build_prompt fills {native_language} from the target
    # language's own NATIVE_LANGUAGE_NAMES mapping.
    prompt = build_prompt("de", "en")
    assert "Englisch" in prompt
    assert "{native_language}" not in prompt


def test_build_prompt_unknown_language_falls_back_to_english():
    prompt = build_prompt("xx", "en")
    english_prompt = build_prompt("en", "en")
    assert prompt == english_prompt


def test_build_prompt_unknown_native_language_falls_back():
    # Should not raise even for a native language code with no dedicated name.
    prompt = build_prompt("de", "zz")
    assert "{native_language}" not in prompt


def test_build_conversation_helper_prompt_arabic():
    prompt = build_conversation_helper_prompt("ar", "en")
    assert "{native_language}" not in prompt
    assert isinstance(prompt, str) and prompt
