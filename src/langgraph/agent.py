import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage, SystemMessage
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


def _plain_text(content) -> str:
    """Flatten a LangChain message's .content into plain text.

    AIMessages generated directly by the graph's own LLM call have a bare
    string .content, but any message that passed through LiveKit's
    ChatContext (src/livekit/adapter/langgraph.py:_chat_ctx_to_state) — every
    HumanMessage, and AIMessages reconstructed from prior turns — has a list
    of content parts instead, e.g. [{"type": "text", "text": "hello"}], since
    LiveKit's ChatMessage.content is always a list, never a bare string.
    Every function here that scans message content must go through this, or
    it silently sees only half the conversation.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
        return " ".join(p for p in parts if p)
    return ""


def _covered_topics(messages: list) -> list[str]:
    """Scan full message history and return labels of topics already discussed."""
    all_text = " ".join(_plain_text(getattr(m, "content", None)).lower() for m in messages)
    return [label for label, keywords in _TOPIC_KEYWORDS if any(kw in all_text for kw in keywords)]


# ── Arabic vocab-card drilling ──────────────────────────────────────────────
# Mirrors the frontend's VOCAB_SETS (src/frontend/static/app.js) — the backend
# has no other way to know which card is on screen or what its items are, so
# this is generated once from that source of truth (see vocab_ar.json). Keep
# the two in sync if the vocab sets change.
_VOCAB_AR_PATH = Path(__file__).parent / "vocab_ar.json"
try:
    _VOCAB_SETS_AR: dict = json.loads(_VOCAB_AR_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    _VOCAB_SETS_AR = {}


def _active_vocab_set_ar(messages: list) -> str | None:
    """Identify which vocab card is currently active by finding its section
    trigger phrase in the conversation (most recent occurrence wins)."""
    for m in reversed(messages):
        content = _plain_text(getattr(m, "content", None))
        if not content:
            continue
        for key, data in _VOCAB_SETS_AR.items():
            trigger = data.get("trigger")
            if trigger and trigger in content:
                return key
    return None


def _vocab_progress_ar(messages: list, set_key: str) -> tuple[list[str], list[str]]:
    """Cheap heuristic fallback: a word counts as introduced once Teddy's own
    message has mentioned it. Used only if the dedicated judge call (below)
    fails — it doesn't verify the child actually answered, just that Teddy
    said the word."""
    data = _VOCAB_SETS_AR.get(set_key)
    if not data:
        return [], []
    ai_text = " ".join(_plain_text(m.content) for m in messages if isinstance(m, AIMessage))
    introduced = [w for w in data["items"] if w in ai_text]
    remaining = [w for w in data["items"] if w not in ai_text]
    return introduced, remaining


_judge_llm: ChatOpenAI | None = None


def _get_judge_llm() -> ChatOpenAI:
    global _judge_llm
    if _judge_llm is None:
        _judge_llm = ChatOpenAI(model=LLM_MODEL, temperature=0)
    return _judge_llm


def _recent_transcript(messages: list, limit: int = 24) -> str:
    """Plain-text transcript of the last `limit` messages, for the judge call."""
    lines = []
    for m in messages[-limit:]:
        content = _plain_text(getattr(m, "content", None)).strip()
        if not content:
            continue
        who = "Teddy" if isinstance(m, AIMessage) else "Child"
        lines.append(f"{who}: {content}")
    return "\n".join(lines)


async def _judge_vocab_progress_ar(messages: list, set_key: str) -> list[str]:
    """Dedicated call whose only job is judging which words have been BOTH
    asked about by Teddy AND answered by the child with an attempted full
    sentence. Kept separate from the persona reply so this judgment doesn't
    get diluted by everything else Teddy has to do in one response — the same
    reasoning behind the separate translation call.

    Falls back to the cheap substring heuristic if the call fails or returns
    something unparseable, so a transient API error can't break the drill.
    """
    data = _VOCAB_SETS_AR.get(set_key)
    if not data:
        return []
    items = data["items"]
    transcript = _recent_transcript(messages)
    if not transcript:
        return []

    system = (
        "You are grading a young child's Arabic vocabulary drill. You will be given an "
        "ordered list of target words and a conversation transcript between Teddy (the "
        "teacher) and the child. A word counts as complete ONLY if there is a clear "
        "back-and-forth about that SPECIFIC word: Teddy asks or prompts about it by name, "
        "AND the child's reply right after that specifically responds to it with at least "
        "an attempted full sentence (a bare single word or fragment does NOT count). "
        "A word Teddy merely mentions in passing — e.g. as part of a personal share, an "
        "example, or alongside other words — does NOT count unless the child was actually "
        "asked about that exact word and then responded to it. When in doubt, do NOT mark "
        "a word complete.\n"
        "Reply with ONLY a JSON array of the completed words, copied EXACTLY as spelled in "
        "the target list, in the order they appear there. If none are complete, reply []."
    )
    human = f"Target words in order: {json.dumps(items, ensure_ascii=False)}\n\nTranscript:\n{transcript}"

    try:
        # tags=["nostream"]: this call happens inside _build_prompt, which runs as
        # part of the SAME graph invocation the adapter is streaming with
        # stream_mode="messages" — without this tag its raw JSON output leaks into
        # the spoken TTS stream alongside Teddy's actual reply.
        result = await _get_judge_llm().ainvoke(
            [("system", system), ("human", human)], config={"tags": ["nostream"]},
        )
        raw = result.content.strip() if isinstance(result.content, str) else "[]"
        # Model sometimes wraps the array in a code fence despite instructions
        raw = raw.strip("`").removeprefix("json").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("judge did not return a list")
        done_set = set(parsed)
        # Preserve canonical order and drop anything not actually in the item list
        return [w for w in items if w in done_set]
    except Exception:
        logger.warning("vocab progress judge failed; falling back to heuristic", exc_info=True)
        introduced, _ = _vocab_progress_ar(messages, set_key)
        return introduced


def _asked_questions(messages: list) -> list[str]:
    """Extract all questions the agent already asked from the full history."""
    questions = []
    for m in messages:
        if not isinstance(m, AIMessage):
            continue
        content = _plain_text(getattr(m, "content", ""))
        if not content:
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


async def _build_prompt(state, config: RunnableConfig) -> list:
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

    # 3. Vocab-card drilling: exactly ONE deterministic word at a time (chosen
    # by code, not left to the model to pick from a list), full-sentence
    # correction, judged completion, full coverage before moving on. Arabic
    # only — no vocab data exists for other learn languages yet.
    if lang_code == "ar":
        active_set = _active_vocab_set_ar(all_messages)
        used_default = False
        if not active_set:
            # No card explicitly selected — default the very first lesson to
            # greetings/introductions (hello, how are you, name, age, where
            # from, job/school) so a brand-new learner gets a structured start
            # instead of free-associating off whatever word they happen to say.
            active_set = "greetings"
            used_default = True

        items = _VOCAB_SETS_AR.get(active_set, {}).get("items", [])
        done = await _judge_vocab_progress_ar(all_messages, active_set)
        remaining = [w for w in items if w not in done]

        if used_default and not remaining:
            # Greetings already fully completed and nothing else was
            # explicitly selected — release into free chat instead of
            # re-drilling greetings forever.
            active_set = None

    if lang_code == "ar" and active_set:
        title = _VOCAB_SETS_AR[active_set]["titleAr"]

        try:
            from langgraph.config import get_stream_writer
            get_stream_writer()({
                "type": "vocab_progress",
                "data": {"set_key": active_set, "done": done, "current": remaining[0] if remaining else None},
            })
        except Exception:
            logger.debug("could not emit vocab_progress custom event", exc_info=True)

        if remaining:
            current_word = remaining[0]
            prompt += (
                f"\n\nVOCAB CARD DRILL — current card: {title}\n"
                f"Words already completed: {', '.join(done) if done else '(none yet)'}\n"
                f"THE WORD TO ASK ABOUT RIGHT NOW, AND ONLY THIS WORD: {current_word}\n"
                "Do not ask about, mention, or move on to any other word from this card until this exact "
                "word has been properly answered — you have no choice in which word to use, it is decided "
                "for you above.\n"
                "CORRECTION RULE — critical, follow every time: if the child answers with only a single "
                f"word or a short fragment instead of a complete sentence about '{current_word}', do NOT "
                "move to a new word. First say the correct complete Arabic sentence they should say (e.g. "
                "'قل: أحب الخبز'), then ask the SAME question again so they can try the full sentence "
                "themselves. Only move on once they attempt a full sentence (it does not need to be perfect).\n"
                "STAY ON TOPIC — critical: this card is the lesson right now. If the child brings up "
                "something unrelated to it, react warmly to what they said in ONE short breath (like a "
                "real friend would), then gently bring them back to the current word or card — do not "
                "just ignore them, and do not abandon the card. Only leave the card early if the child "
                "clearly and repeatedly says they want to stop or do something else.\n"
                "DO NOT let a single ambiguous word pull you onto a new subject — e.g. if the child says "
                "'حلو' (which can just mean 'cool!'/'nice!'), do not assume they mean dessert and start "
                "asking about sweets or cake. Only follow a new subject if the child clearly and directly "
                "asks about it in a full sentence.\n"
                "NATIVE-LANGUAGE ANSWERS COUNT: if the child answers in their native language instead of "
                "Arabic (e.g. says the English word for the current word), treat that as their attempt at "
                "THIS word, not a new topic — confirm it's right, give the correct Arabic word/sentence, "
                "and apply the CORRECTION RULE above (model it, then re-ask) rather than changing subject."
            )
        else:
            prompt += (
                f"\n\nVOCAB CARD COMPLETE — every word in '{title}' has been completed! "
                "Warmly congratulate the child, then ASK them (do not just decide for them) whether they "
                "want to keep talking about this topic a bit more, or move on to something new. Follow "
                "whatever they choose — do not push a new topic on them and do not force them off it."
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


