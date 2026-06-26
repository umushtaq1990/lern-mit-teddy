import logging
import os
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from .prompts import build_prompt as _build_lingua_prompt

logger = logging.getLogger(__name__)

load_dotenv()

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-nano")

_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ar": "Arabic",
    "zh": "Chinese (Mandarin)",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ru": "Russian",
    "tr": "Turkish",
    "hi": "Hindi",
}


def get_langfuse_config() -> dict:
    """Enable Langfuse tracing when local Langfuse keys are configured."""
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        return {}
    if os.getenv("LANGFUSE_HOST") and not os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_BASE_URL"] = os.environ["LANGFUSE_HOST"]
    from langfuse.langchain import CallbackHandler
    return {"callbacks": [CallbackHandler()]}




_MAX_RECENT = 16  # messages passed as context; full history is scanned separately for topic tracking

# Each entry: (human-readable label, keywords to detect in message text)
_TOPIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("how they are feeling",          ["geht", "gut", "schlecht", "müde", "super", "toll", "prima"]),
    ("their name",                     ["heiße", "heißt", "name"]),
    ("their age",                      ["alt", "jahre"]),
    ("what they ate for breakfast",    ["gefrühstückt", "frühstück", "gegessen", "getrunken"]),
    ("whether they brushed their teeth", ["zähne", "geputzt"]),
    ("whether they took a shower",     ["geduscht", "dusche", "dusch"]),
    ("what they like to play",         ["spielst", "spiele", "spielen"]),
    ("their family / siblings",        ["geschwister", "bruder", "schwester", "familie"]),
]


def _covered_topics(messages: list) -> list[str]:
    """Scan full message history and return labels of topics already discussed."""
    from langchain_core.messages import AIMessage
    all_text = " ".join(
        m.content.lower()
        for m in messages
        if hasattr(m, "content") and isinstance(m.content, str)
    )
    return [label for label, keywords in _TOPIC_KEYWORDS if any(kw in all_text for kw in keywords)]


def _asked_questions(messages: list) -> list[str]:
    """Extract all questions the agent already asked from the full history."""
    from langchain_core.messages import AIMessage
    questions = []
    for m in messages:
        if not isinstance(m, AIMessage):
            continue
        content = getattr(m, "content", "")
        if not isinstance(content, str):
            continue
        # Split on sentence endings and collect anything ending with ?
        for part in content.replace("?", "?\n").splitlines():
            part = part.strip()
            if part.endswith("?") and len(part) > 6:
                questions.append(part)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for q in questions:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


def _build_prompt(state, config: RunnableConfig) -> list:
    """Inject language-specific instructions from LangGraph call config."""
    configurable = config.get("configurable") or {}
    lang_code   = configurable.get("language", "de")   # default German
    native_code = configurable.get("native_language", "en")
    learning_language = _LANGUAGE_NAMES.get(lang_code, "German")
    native_language   = _LANGUAGE_NAMES.get(native_code, "English")
    logger.info("_build_prompt: lang=%s native=%s configurable=%s", lang_code, native_code, configurable)
    prompt = _build_lingua_prompt(lang_code, native_code)

    all_messages = state["messages"]

    # 1. Keyword-based topic summary (8 fixed topics)
    covered = _covered_topics(all_messages)
    if covered:
        prompt += (
            "\n\nTOPICS ALREADY COVERED — do NOT ask about these again:\n"
            + "\n".join(f"  ✓ {t}" for t in covered)
        )

    # 2. Exact questions already asked (catches free-chat repeats like colors, animals)
    asked = _asked_questions(all_messages)
    if asked:
        prompt += (
            "\n\nQUESTIONS YOU ALREADY ASKED — never repeat these:\n"
            + "\n".join(f"  - {q}" for q in asked)
            + "\nAsk something NEW instead."
        )

    # Reminder injected just before the latest message so the LLM can't forget it
    prompt += f"\n\nREMINDER: Your NEXT reply must be in {learning_language} only. Not one word of {native_language}."

    # Only pass the most recent messages as context (keeps LLM fast)
    recent = all_messages[-_MAX_RECENT:] if len(all_messages) > _MAX_RECENT else all_messages
    return [SystemMessage(content=prompt)] + recent


langfuse_config = get_langfuse_config()

agent = create_react_agent(
    model=ChatOpenAI(model=LLM_MODEL),
    tools=[],
    prompt=_build_prompt,
    name="lingua_ai_agent",
    checkpointer=MemorySaver(),
)

if langfuse_config:
    agent = agent.with_config(langfuse_config)


