"""
LangGraphAdapter bridges LiveKit Agents' LLM interface to a LangGraph workflow.

Key ideas:
- We stream LangGraph outputs using stream_mode=["messages", "custom"].
- "messages" chunks are converted to LiveKit llm.ChatChunk with ChoiceDelta(content=str).
- "custom" chunks support simple events like {"type": "say", data: {content: str}}.

References:
- LiveKit Agents LLM API (ChatChunk, ChoiceDelta): docs/livekit/agents (repo README and llm module)
- LangGraph streaming modes: messages/custom and astream():
  https://github.com/langchain-ai/langgraph/blob/main/docs/docs/how-tos/streaming.md
- RemoteGraph astream usage:
  https://github.com/langchain-ai/langgraph/blob/main/docs/docs/how-tos/use-remote-graph.md
"""

from typing import Any, Awaitable, Callable, Optional
import base64
from httpx import HTTPStatusError
from livekit.agents import llm
from livekit.agents.types import (
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    NotGivenOr,
)
from livekit.agents.utils import shortuuid
from livekit.agents.llm.tool_context import FunctionTool, RawFunctionTool, ToolChoice
from livekit.agents.utils.images import encode, EncodeOptions
try:
    # Prefer concrete ImageContent class if available
    from livekit.agents.llm import ImageContent as LKImageContent  # type: ignore
except Exception:  # pragma: no cover
    LKImageContent = None  # sentinel; we'll fallback to hasattr checks
from langgraph.pregel import Pregel
from langchain_core.messages import BaseMessageChunk, AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from langgraph.errors import GraphInterrupt
from langchain_openai import ChatOpenAI

from ..config import SUPPORTED_LANGUAGES

import logging
import os

logger = logging.getLogger(__name__)

# Dedicated translator for the on-screen caption — deliberately separate from the
# main persona LLM call. Asking one call to speak in-character AND produce a
# translation with a formatting marker proved unreliable (the model would
# sometimes drop the marker, or let English leak into the spoken reply). A
# second, single-purpose call has one job and nothing else to get wrong.
_TRANSLATOR_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
_translator: ChatOpenAI | None = None


def _get_translator() -> ChatOpenAI:
    global _translator
    if _translator is None:
        _translator = ChatOpenAI(model=_TRANSLATOR_MODEL, temperature=0)
    return _translator


async def _translate(text: str, target_language_name: str) -> str:
    """Translate a short spoken reply into target_language_name. Best-effort —
    caller treats an empty/failed result as "no caption this turn"."""
    if not text.strip():
        return ""
    messages = [
        (
            "system",
            f"Translate the following short text into {target_language_name}. "
            "Reply with ONLY the translation — no quotes, no notes, no original text.",
        ),
        ("human", text),
    ]
    result = await _get_translator().ainvoke(messages)
    content = result.content
    return content.strip() if isinstance(content, str) else ""


class LangGraphStream(llm.LLMStream):
    """LLMStream implementation that proxies a LangGraph stream.

    - Creates LiveKit ChatChunks from LangGraph "messages" stream chunks.
    - Passes through simple custom events (e.g., "say") from LangGraph "custom" stream.

    See:
      - LangGraph stream modes: https://github.com/langchain-ai/langgraph/blob/main/docs/docs/how-tos/streaming.md
      - LiveKit LLM stream contract: livekit.agents.llm.LLMStream (in repo)
    """

    def __init__(
        self,
        llm: llm.LLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[FunctionTool | RawFunctionTool],
        conn_options: APIConnectOptions,
        graph: Pregel,
        langfuse_handler: Any = None,
        on_caption: Callable[[str, str], Awaitable[None]] | None = None,
        on_turn: Callable[[str, str], Awaitable[None]] | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ):
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._graph = graph
        self._langfuse_handler = langfuse_handler
        self._on_caption = on_caption
        self._on_turn = on_turn
        self._on_progress = on_progress
        # One LangGraphStream instance == one turn, so a single id per instance is
        # enough to let the frontend tell captions from different turns apart.
        self._turn_id = shortuuid()
        self._spoken_parts: list[str] = []  # accumulates the full reply for translation

    @staticmethod
    def _plain_text(content: Any) -> str:
        """Flatten a LangChain message's .content into plain text — it's a plain
        str for AI/system messages, but ChatContext-derived HumanMessages carry
        a list of content parts (e.g. [{"type": "text", "text": "hello"}]) since
        LiveKit's ChatMessage.content is always a list, never a bare string."""
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

    async def _log_turn(self, role: str, text: str) -> None:
        if not self._on_turn or not text:
            return
        try:
            await self._on_turn(role, text)
        except Exception:
            logger.warning("on_turn callback failed", exc_info=True)

    async def _run(self):
        """Consume LangGraph stream and emit LiveKit ChatChunks."""
        state = self._chat_ctx_to_state()

        # see if we need to respond to an interrupt (resume)
        if interrupt := await self._get_interrupt():
            used_messages = [AIMessage(interrupt.value)]
            # resume with last user content if any
            last_user = next(
                (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
                None,
            )
            if last_user:
                used_messages.append(last_user)
                input_state = Command(resume=(last_user.content, used_messages))
            else:
                input_state = Command(resume=(interrupt.value, used_messages))
        else:
            input_state = state

        # Log the user's latest turn (whatever this stream is responding to)
        last_human = next(
            (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
            None,
        )
        if last_human:
            user_text = self._plain_text(last_human.content)
            if user_text:
                await self._log_turn("user", user_text)

        configurable = (self._llm._config or {}).get("configurable") or {}
        native_language = SUPPORTED_LANGUAGES.get(configurable.get("native_language", "en"), "English")

        try:
            # Merge Langfuse callback into graph config so every LLM call is traced
            run_config = dict(self._llm._config or {})
            if self._langfuse_handler is not None:
                existing = list(run_config.get("callbacks", []))
                run_config["callbacks"] = [self._langfuse_handler] + existing

            # LangGraph astream with explicit modes (messages, custom)
            # https://github.com/livekit/agents/blob/main/docs/docs/how-tos/streaming.md
            async for mode, data in self._graph.astream(
                input_state, config=run_config, stream_mode=["messages", "custom"]
            ):
                if mode == "messages":
                    if data and len(data) > 0:
                        self._forward(data[0])

                if mode == "custom":
                    # Minimal custom protocol: {"type": "say", data: {content: str}}
                    if isinstance(data, dict) and (event := data.get("type")):
                        if event == "say":
                            content = (data.get("data") or {}).get("content")
                            self._forward(content)
                        elif event == "vocab_progress" and self._on_progress:
                            try:
                                await self._on_progress(data.get("data") or {})
                            except Exception:
                                logger.warning("on_progress callback failed", exc_info=True)
        except GraphInterrupt:
            # Graph was interrupted; we gracefully stop streaming
            pass

        # If interrupted late, send the string as a message
        if interrupt := await self._get_interrupt():
            content, _ = self._extract_content(interrupt.value)
            if content and (chunk := self._create_livekit_chunk(content)):
                self._event_ch.send_nowait(chunk)
                self._spoken_parts.append(content)

        await self._log_turn("assistant", "".join(self._spoken_parts).strip())
        await self._dispatch_translation(native_language)

    def _forward(self, msg: BaseMessageChunk | str | None) -> None:
        """Extract content from a stream chunk, forward it to TTS, and keep a
        copy for the end-of-turn translation pass."""
        content, request_id = self._extract_content(msg)
        if not content:
            return
        self._spoken_parts.append(content)
        if chunk := self._create_livekit_chunk(content, id=request_id):
            self._event_ch.send_nowait(chunk)

    async def _dispatch_translation(self, native_language: str) -> None:
        """Translate the full turn's reply and send it via on_caption — a separate,
        single-purpose call so the main persona LLM never has to juggle speaking
        in-character AND producing a formatted translation in the same response."""
        if not self._on_caption:
            return
        text = "".join(self._spoken_parts).strip()
        if not text:
            return
        try:
            translation = await _translate(text, native_language)
            if translation:
                await self._on_caption(translation, self._turn_id)
                await self._log_turn("translation", translation)
        except Exception:
            logger.warning("translation dispatch failed", exc_info=True)

    def _chat_ctx_to_state(self) -> dict[str, Any]:
        """Translate LiveKit ChatContext into LangGraph state messages.

        We map LiveKit roles to LangChain message classes (AIMessage/HumanMessage/SystemMessage).
        """
        messages: list[AIMessage | HumanMessage | SystemMessage] = []
        for item in getattr(self._chat_ctx, "items", []):
            if getattr(item, "type", None) != "message":
                continue
            role = getattr(item, "role", None)
            item_id = getattr(item, "id", None)

            # Prefer rich content if available, else fallback to text_content
            content_out: Any
            raw_content = getattr(item, "content", None)
            text_content = getattr(item, "text_content", None)

            if isinstance(raw_content, list) and raw_content:
                parts: list[dict[str, Any]] = []
                for c in raw_content:
                    if isinstance(c, str):
                        parts.append({"type": "text", "text": c})
                    elif (LKImageContent and isinstance(c, LKImageContent)) or hasattr(c, "image"):
                        img_obj = getattr(c, "image", None)
                        if isinstance(img_obj, str):
                            parts.append({"type": "image_url", "image_url": {"url": img_obj}})
                        else:
                            try:
                                img_bytes = encode(img_obj, EncodeOptions(format="JPEG"))
                                data_url = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('utf-8')}"
                                parts.append({"type": "image_url", "image_url": {"url": data_url}})
                            except Exception:
                                logger.warning("Unsupported image in ChatContext; skipping image part")
                    else:
                        logger.warning("Unsupported content type in ChatContext message; skipping")
                content_out = parts if parts else (text_content or "")
            else:
                # Fallback to text only
                if not text_content:
                    continue
                content_out = text_content

            if role == "assistant":
                messages.append(AIMessage(content=content_out, id=item_id))
            elif role == "user":
                messages.append(HumanMessage(content=content_out, id=item_id))
            # System messages are intentionally excluded: LangGraph's _build_prompt
            # generates the authoritative system message from the per-language prompt
            # files. Passing LiveKit's Agent.instructions here would create a second
            # conflicting system message and override the target language.

        return {"messages": messages}

    async def _get_interrupt(self) -> Optional[str]:
        """Inspect graph state for latest assistant interrupt string.

        Uses Pregel.aget_state to retrieve interrupts from tasks.
        https://github.com/langchain-ai/langgraph/blob/main/docs/docs/reference/pregel.md
        """
        try:
            state = await self._graph.aget_state(config=self._llm._config)
            interrupts = [
                interrupt for task in state.tasks for interrupt in task.interrupts
            ]
            assistant = next(
                (
                    interrupt
                    for interrupt in reversed(interrupts)
                    if isinstance(interrupt.value, str)
                ),
                None,
            )
            return assistant
        except HTTPStatusError:
            return None
        except (TypeError, AttributeError, KeyError) as e:
            # Handle the case where state or checkpoint is None
            logger.warning(f"Error getting interrupt state: {e}")
            return None

    @staticmethod
    def _create_livekit_chunk(
        content: str,
        *,
        id: str | None = None,
    ) -> llm.ChatChunk | None:
        # ChoiceDelta.content must be a string
        return llm.ChatChunk(
            id=id or shortuuid(),
            delta=llm.ChoiceDelta(role="assistant", content=content),
        )

    @staticmethod
    def _extract_content(
        msg: BaseMessageChunk | str | None,
    ) -> tuple[str | None, str | None]:
        """Normalize a LangGraph message chunk or string into (content, request_id).

        Accepts:
          - str content
          - message-like objects with .content (str)
          - dicts with {id?, content?}
          - lists where first element carries the content
        Returns (None, None) when content is missing or not a string.
        """
        if not msg:
            return None, None

        if isinstance(msg, ToolMessage) or getattr(msg, "type", None) == "tool":
            return None, None

        request_id = None
        content = msg

        if isinstance(msg, str):
            content = msg
        elif hasattr(msg, "content") and isinstance(msg.content, str):
            request_id = getattr(msg, "id", None)
            content = msg.content
        elif isinstance(msg, dict):
            request_id = msg.get("id")
            content = msg.get("content")
        elif isinstance(msg, list):
            # Handle case where msg is a list - try to extract content from first item
            if msg and len(msg) > 0:
                first_item = msg[0]
                if isinstance(first_item, str):
                    content = first_item
                elif hasattr(first_item, "content") and isinstance(first_item.content, str):
                    content = first_item.content
                    request_id = getattr(first_item, "id", None)
                elif isinstance(first_item, dict):
                    content = first_item.get("content", "")
                    request_id = first_item.get("id")
                else:
                    logger.warning(f"Unsupported message type in list: {type(first_item)}")
                    return None, None
            else:
                logger.warning("Empty message list received")
                return None, None
        else:
            logger.warning(f"Unsupported message type: {type(msg)}")
            return None, None

        # Ensure content is a string
        if not isinstance(content, str):
            logger.warning(f"Content is not a string: {type(content)}")
            return None, None

        return content, request_id


class LangGraphAdapter(llm.LLM):
    """Adapter that exposes a LangGraph agent as a LiveKit LLM.

    chat() creates a LangGraphStream that maps ChatContext + tools into
    the agent execution. Tools are passed through so LiveKit can advertise
    capabilities to the calling side when applicable.

    See LiveKit LLM.chat signature and LLMStream contract in the docs.
    """

    def __init__(
        self,
        graph: Any,
        config: dict[str, Any] | None = None,
        langfuse_handler: Any = None,
        on_caption: Callable[[str, str], Awaitable[None]] | None = None,
        on_turn: Callable[[str, str], Awaitable[None]] | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ):
        super().__init__()
        self._graph = graph
        self._config = config
        self._langfuse_handler = langfuse_handler
        self._on_caption = on_caption
        self._on_turn = on_turn
        self._on_progress = on_progress

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[FunctionTool | RawFunctionTool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        """Create a streaming session backed by the provided LangGraph.

        - chat_ctx: prior conversation context from LiveKit
        - tools: tool definitions (forwarded to base stream for metadata)
        - conn_options: stream connection options
        """
        return LangGraphStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            graph=self._graph,
            langfuse_handler=self._langfuse_handler,
            on_caption=self._on_caption,
            on_turn=self._on_turn,
            on_progress=self._on_progress,
        )