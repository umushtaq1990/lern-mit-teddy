"""Offline prompt/judge evaluation run, logged to MLflow.

Standalone tool — NOT part of the live request path (the live app only uses
Langfuse for production tracing). Run manually whenever you change a prompt
file, the vocab-card drill logic, or the judge prompt in
src/langgraph/agent.py, to compare the new behavior against a fixed set of
sample conversations:

    uv run python -m src.langgraph.eval.run_eval

Then open the MLflow UI (settings.mlflow_tracking_uri — docker-compose's
`mlflow` service, or a local `mlflow ui` pointed at the same URI) to browse
runs and compare prompt iterations over time.

This makes real OpenAI API calls (it exercises the actual agent), so it
needs a real OPENAI_API_KEY in your environment — it is not run in CI.
"""

from __future__ import annotations

import time
import uuid

import mlflow
from langchain_core.messages import HumanMessage

from src.langgraph.agent import get_agent
from src.settings import get_settings

# A small, fixed set of sample conversations — representative of each
# language/mode combination the agent handles. Extend this list as new
# lesson modes or languages are added; keep it small enough to run in
# under a minute so it stays something you'll actually run before shipping
# a prompt change, not something you'll put off.
SAMPLE_CONVERSATIONS: list[dict] = [
    {
        "name": "de_greeting",
        "language": "de",
        "native_language": "en",
        "messages": ["Hallo!"],
    },
    {
        "name": "ar_greeting",
        "language": "ar",
        "native_language": "en",
        "messages": ["مرحبا"],
    },
    {
        "name": "ar_conversation_helper",
        "language": "ar",
        "native_language": "en",
        "lesson_mode": "conversation_helper",
        "messages": ["How do I say good morning in Arabic?"],
    },
    {
        "name": "en_free_chat",
        "language": "en",
        "native_language": "en",
        "messages": ["Hi, my name is Sam and I like dogs."],
    },
]


def _run_sample(sample: dict) -> dict:
    agent = get_agent()
    thread_id = str(uuid.uuid4())
    config = {
        "configurable": {
            "thread_id": thread_id,
            "language": sample["language"],
            "native_language": sample["native_language"],
            "lesson_mode": sample.get("lesson_mode", "vocab"),
        }
    }

    start = time.monotonic()
    result = agent.invoke(
        {"messages": [HumanMessage(content=text) for text in sample["messages"]]},
        config=config,
    )
    latency_s = time.monotonic() - start

    reply = result["messages"][-1].content if result.get("messages") else ""
    return {"latency_s": latency_s, "reply": reply}


def main() -> None:
    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("lingua-ai-prompt-eval")

    with mlflow.start_run():
        mlflow.log_param("llm_model", settings.llm_model)
        mlflow.log_param("sample_count", len(SAMPLE_CONVERSATIONS))

        total_latency = 0.0
        for sample in SAMPLE_CONVERSATIONS:
            outcome = _run_sample(sample)
            total_latency += outcome["latency_s"]
            mlflow.log_metric(f"latency_s_{sample['name']}", outcome["latency_s"])
            print(f"[{sample['name']}] {outcome['latency_s']:.2f}s -> {outcome['reply'][:120]!r}")

        mlflow.log_metric("avg_latency_s", total_latency / len(SAMPLE_CONVERSATIONS))


if __name__ == "__main__":
    main()
