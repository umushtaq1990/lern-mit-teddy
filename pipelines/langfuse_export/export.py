"""Daily export: Langfuse traces -> Azure SQL (session/user metadata) + Blob Storage (full transcripts).

Runs as a scheduled Azure Container Apps Job. Standalone by design: does not
import anything from src/ (the live voice-agent code), so it has no dependency
on OPENAI_API_KEY or any other live-call secret — just Langfuse + Azure creds.

The domain-agnostic ETL plumbing (Langfuse pagination, usage/feedback
extraction, SQL upsert, blob naming) lives in ai_platform_shared.export_etl —
shared with any other project exporting Langfuse traces the same way. Only
this app's own trace-tag filter, transcript-turn reconstruction, and
`users`/`sessions` table shape stay local.

State: a single row in the `export_state` SQL table tracks the timestamp of the
last successfully processed trace, so each run only fetches what's new.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import pymssql
from azure.storage.blob import BlobServiceClient

from ai_platform_shared.export_etl import (
    LangfuseRestClient,
    blob_path_for,
    fetch_new_trace_ids,
    fetch_trace,
    find_feedback,
    get_last_run_until,
    sanitize_identifier,
    set_last_run_until,
    summarize_usage,
    to_sql_datetime,
    upsert_generic,
)

LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
LANGFUSE_HOST = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com"

SQL_SERVER = os.environ["SQL_SERVER"]
SQL_DATABASE = os.environ["SQL_DATABASE"]
SQL_USER = os.environ["SQL_USER"]
SQL_PASSWORD = os.environ["SQL_PASSWORD"]

STORAGE_CONNECTION_STRING = os.environ["STORAGE_CONNECTION_STRING"]
STORAGE_CONTAINER = os.environ.get("STORAGE_CONTAINER", "transcripts")

JOB_NAME = "langfuse_export"
VOICE_CALL_TAG = "voice-call"


def _log(msg: str) -> None:
    print(f"[langfuse_export] {msg}", flush=True)


# ── Transcript reconstruction (app-specific — stays local) ─────────────────

def build_transcript(trace: dict) -> list[dict[str, str]]:
    """Build the turn-by-turn chat from 'turn' events emitted by the real STT/TTS
    pipeline (VoiceSessionTracer.turn_event), NOT from LangGraph's internal
    human/ai message state — that state can include injected non-speech
    messages and doesn't reliably map to who actually said what.
    """
    turn_events = [o for o in trace.get("observations", []) if o.get("name") == "turn"]
    turn_events.sort(key=lambda o: o.get("startTime") or "")

    turns: list[dict[str, str]] = []
    for o in turn_events:
        meta = o.get("metadata") or {}
        role = meta.get("role")
        text = (meta.get("text") or "").strip()
        if not role or not text:
            continue
        turns.append({"role": role, "content": text})
    return turns


def main() -> None:
    langfuse = LangfuseRestClient(host=LANGFUSE_HOST, public_key=LANGFUSE_PUBLIC_KEY, secret_key=LANGFUSE_SECRET_KEY)
    conn = pymssql.connect(server=SQL_SERVER, user=SQL_USER, password=SQL_PASSWORD, database=SQL_DATABASE)
    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    container = blob_service.get_container_client(STORAGE_CONTAINER)

    since_iso = get_last_run_until(conn, JOB_NAME)
    _log(f"fetching traces since={since_iso or '(beginning)'}")

    trace_ids = fetch_new_trace_ids(langfuse, tag=VOICE_CALL_TAG, since_iso=since_iso)
    _log(f"found {len(trace_ids)} new trace(s)")

    latest_timestamp = since_iso
    processed = 0

    for trace_id in trace_ids:
        trace = fetch_trace(langfuse, trace_id)
        metadata = trace.get("metadata") or {}
        session_id = trace.get("sessionId") or trace_id
        user_id = sanitize_identifier(trace.get("userId") or metadata.get("participant") or "unknown")
        display_name = trace.get("userId") or user_id

        started_at = trace.get("timestamp")
        ended_at = trace.get("updatedAt") or started_at
        transcript = build_transcript(trace)
        usage = summarize_usage(trace)
        feedback_rating, feedback_comment = find_feedback(trace)

        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        duration_seconds = max(0, round((end_dt - start_dt).total_seconds()))

        blob_name = blob_path_for(start_dt, user_id, session_id)
        trace_url = f"{LANGFUSE_HOST}/project/{trace.get('projectId')}/traces/{trace_id}"

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "room": metadata.get("room") or session_id,
            "language": metadata.get("language"),
            "native_language": metadata.get("native_language"),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "langfuse_trace_url": trace_url,
            "llm_model": metadata.get("llm_model"),
            "stt_model": metadata.get("stt_model"),
            "tts_model": metadata.get("tts_model"),
            "usage": usage,
            "feedback_rating": feedback_rating,
            "feedback_comment": feedback_comment,
            "turns": transcript,
        }
        container.upload_blob(name=blob_name, data=json.dumps(payload, ensure_ascii=False, indent=2), overwrite=True)

        upsert_generic(
            conn,
            table="users",
            key_col="user_id",
            row={"user_id": user_id, "display_name": display_name},
            update_on_match=False,
        )
        upsert_generic(
            conn,
            table="sessions",
            key_col="session_id",
            row={
                "session_id": session_id,
                "user_id": user_id,
                "room": payload["room"],
                "language": payload["language"],
                "native_language": payload["native_language"],
                "started_at": to_sql_datetime(started_at),
                "ended_at": to_sql_datetime(ended_at),
                "turn_count": len(transcript),
                "langfuse_trace_url": trace_url,
                "blob_path": blob_name,
                "llm_model": payload["llm_model"],
                "stt_model": payload["stt_model"],
                "tts_model": payload["tts_model"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
                "estimated_cost_usd": usage["estimated_cost_usd"],
                "duration_seconds": duration_seconds,
                "feedback_rating": feedback_rating,
                "feedback_comment": feedback_comment,
            },
            extra_update_sql="exported_at = SYSUTCDATETIME()",
        )

        processed += 1
        if latest_timestamp is None or started_at > latest_timestamp:
            latest_timestamp = started_at

    if latest_timestamp:
        set_last_run_until(conn, JOB_NAME, to_sql_datetime(latest_timestamp))

    conn.close()
    _log(f"done — processed {processed} session(s)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        _log(f"FAILED: {exc}")
        sys.exit(1)
