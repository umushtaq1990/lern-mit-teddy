"""Tests for src.langgraph.agent._build_prompt — the core per-turn prompt
logic — exercised directly with no LLM/agent construction involved.

This is possible because importing src.langgraph.agent has zero side effects
(get_agent() builds the real ChatOpenAI-backed graph lazily, only when
called) and reset_agent_caches() (via the autouse reset_agent_state fixture
in conftest.py) keeps the module's judge-cache/word-attempt state from
leaking between tests.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.langgraph import agent as agent_module


def _config(**configurable) -> dict:
    return {"configurable": configurable}


async def test_build_prompt_english_has_no_vocab_drill():
    """English has no vocab_data.json entries, so no card/judge logic should
    engage — this exercises the free-chat topic-tracking path only."""
    state = {"messages": [HumanMessage(content="Hi, my name is Sam")]}
    result = await agent_module._build_prompt(state, _config(language="en", native_language="en"))

    assert isinstance(result[0], SystemMessage)
    assert "English only" in result[0].content or "your NEXT reply" in result[0].content.lower()
    # original messages are preserved after the injected system message
    assert result[1:] == state["messages"]


async def test_build_prompt_tracks_covered_topics():
    messages = [
        HumanMessage(content="Mir geht es gut"),
        AIMessage(content="Toll!"),
    ]
    result = await agent_module._build_prompt(
        {"messages": messages}, _config(language="de", native_language="en")
    )
    system_prompt = result[0].content
    assert "TOPICS ALREADY COVERED" in system_prompt


async def test_build_prompt_deduplicates_asked_questions():
    messages = [AIMessage(content="Wie heißt du?")]
    result = await agent_module._build_prompt(
        {"messages": messages}, _config(language="de", native_language="en")
    )
    system_prompt = result[0].content
    assert "QUESTIONS YOU ALREADY ASKED" in system_prompt
    assert "Wie heißt du?" in system_prompt


async def test_build_prompt_vocab_drill_defaults_to_greetings(monkeypatch):
    """German has vocab data; with no card explicitly triggered yet, the first
    lesson should default to the 'greetings' card."""
    monkeypatch.setattr(
        agent_module, "_judge_vocab_progress", lambda *a, **k: _async_result([])
    )
    messages = [HumanMessage(content="Hallo")]
    result = await agent_module._build_prompt(
        {"messages": messages},
        _config(language="de", native_language="en", thread_id="t1"),
    )
    system_prompt = result[0].content
    assert "VOCAB CARD DRILL" in system_prompt

    # Let the background judge-refresh task (fire-and-forget) finish so it
    # doesn't leak into the next test as a pending task.
    task = next(iter(agent_module._state.judge_tasks.values()))
    await task


async def test_build_prompt_conversation_helper_mode_skips_vocab_drill():
    messages = [HumanMessage(content="How do I say hello in Arabic?")]
    result = await agent_module._build_prompt(
        {"messages": messages},
        _config(language="ar", native_language="en", lesson_mode="conversation_helper"),
    )
    system_prompt = result[0].content
    assert "VOCAB CARD DRILL" not in system_prompt


async def _async_result(value):
    return value
