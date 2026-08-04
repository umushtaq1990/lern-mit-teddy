"""Daily export: Langfuse traces -> Azure SQL (session/user metadata) + Blob Storage (full transcripts).

Runs as a scheduled Azure Container Apps Job. Standalone by design: does not
import anything from src/ (the live voice-agent code), so it has no dependency
on OPENAI_API_KEY or any other live-call secret — just Langfuse + Azure creds.

State: a single row in the `export_state` SQL table tracks the timestamp of the
last successfully processed trace, so each run only fetches what's new.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import pymssql
import requests
from azure.storage.blob import BlobServiceClient

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
TRACE_NAME_FILTER = None  # traces aren't reliably named "voice-session" at the top level; filter by tag instead
VOICE_CALL_TAG = "voice-call"
PAGE_LIMIT = 50


def _log(msg: str) -> None:
    print(f"[langfuse_export] {msg}", flush=True)


# ── Langfuse API ────────────────────────────────────────────────────────────

def _langfuse_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    resp = requests.get(
        f"{LANGFUSE_HOST}{path}",
        params=params,
        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_new_trace_ids(since_iso: str | None) -> list[str]:
    """List voice-call trace IDs created after `since_iso`, oldest first."""
    ids: list[str] = []
    page = 1
    while True:
        params: dict[str, Any] = {"page": page, "limit": PAGE_LIMIT, "tags": VOICE_CALL_TAG, "orderBy": "timestamp.asc"}
        if since_iso:
            params["fromTimestamp"] = since_iso
        data = _langfuse_get("/api/public/traces", params)
        items = data.get("data", [])
        if not items:
            break
        ids.extend(t["id"] for t in items)
        meta = data.get("meta", {})
        if page >= meta.get("totalPages", page):
            break
        page += 1
    return ids


def fetch_trace(trace_id: str) -> dict[str, Any]:
    return _langfuse_get(f"/api/public/traces/{trace_id}", {})


# ── Transcript reconstruction ────────────────────────────────────────────────

def build_transcript(trace: dict[str, Any]) -> list[dict[str, str]]:
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


# ── SQL ──────────────────────────────────────────────────────────────────────

def get_last_run_until(conn: pymssql.Connection) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT last_run_until FROM export_state WHERE job_name = %s", (JOB_NAME,))
    row = cur.fetchone()
    if row and row[0]:
        return row[0].replace(tzinfo=timezone.utc).isoformat()
    return None


def set_last_run_until(conn: pymssql.Connection, until_iso: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        MERGE export_state AS target
        USING (SELECT %s AS job_name, %s AS last_run_until) AS src
        ON target.job_name = src.job_name
        WHEN MATCHED THEN UPDATE SET last_run_until = src.last_run_until
        WHEN NOT MATCHED THEN INSERT (job_name, last_run_until) VALUES (src.job_name, src.last_run_until);
        """,
        (JOB_NAME, until_iso),
    )
    conn.commit()


def upsert_user(conn: pymssql.Connection, user_id: str, display_name: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        MERGE users AS target
        USING (SELECT %s AS user_id, %s AS display_name) AS src
        ON target.user_id = src.user_id
        WHEN NOT MATCHED THEN INSERT (user_id, display_name) VALUES (src.user_id, src.display_name);
        """,
        (user_id, display_name),
    )
    conn.commit()


def upsert_session(conn: pymssql.Connection, row: dict[str, Any]) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        MERGE sessions AS target
        USING (SELECT %s AS session_id) AS src
        ON target.session_id = src.session_id
        WHEN MATCHED THEN UPDATE SET
            user_id = %s, room = %s, language = %s, native_language = %s,
            started_at = %s, ended_at = %s, turn_count = %s,
            langfuse_trace_url = %s, blob_path = %s, exported_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT
            (session_id, user_id, room, language, native_language, started_at, ended_at,
             turn_count, langfuse_trace_url, blob_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (
            row["session_id"],
            row["user_id"], row["room"], row["language"], row["native_language"],
            row["started_at"], row["ended_at"], row["turn_count"],
            row["langfuse_trace_url"], row["blob_path"],
            row["session_id"], row["user_id"], row["room"], row["language"], row["native_language"],
            row["started_at"], row["ended_at"], row["turn_count"],
            row["langfuse_trace_url"], row["blob_path"],
        ),
    )
    conn.commit()


# ── Main ─────────────────────────────────────────────────────────────────────

def _sanitize(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_") or "unknown"


def _to_sql_datetime(iso_str: str) -> str:
    """Strip the trailing 'Z' so SQL Server's datetime2 parses it as plain UTC."""
    return iso_str[:-1] if iso_str.endswith("Z") else iso_str


def main() -> None:
    conn = pymssql.connect(server=SQL_SERVER, user=SQL_USER, password=SQL_PASSWORD, database=SQL_DATABASE)
    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    container = blob_service.get_container_client(STORAGE_CONTAINER)

    since_iso = get_last_run_until(conn)
    _log(f"fetching traces since={since_iso or '(beginning)'}")

    trace_ids = fetch_new_trace_ids(since_iso)
    _log(f"found {len(trace_ids)} new trace(s)")

    latest_timestamp = since_iso
    processed = 0

    for trace_id in trace_ids:
        trace = fetch_trace(trace_id)
        metadata = trace.get("metadata") or {}
        session_id = trace.get("sessionId") or trace_id
        user_id = _sanitize(trace.get("userId") or metadata.get("participant") or "unknown")
        display_name = trace.get("userId") or user_id

        started_at = trace.get("timestamp")
        ended_at = trace.get("updatedAt") or started_at
        transcript = build_transcript(trace)

        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        blob_name = f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{user_id}__{session_id}.json"
        trace_url = f"{LANGFUSE_HOST}/project/{trace.get('projectId')}/traces/{trace_id}"

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "room": metadata.get("room") or session_id,
            "language": metadata.get("language"),
            "native_language": metadata.get("native_language"),
            "started_at": started_at,
            "ended_at": ended_at,
            "langfuse_trace_url": trace_url,
            "turns": transcript,
        }
        container.upload_blob(name=blob_name, data=json.dumps(payload, ensure_ascii=False, indent=2), overwrite=True)

        upsert_user(conn, user_id, display_name)
        upsert_session(conn, {
            "session_id": session_id,
            "user_id": user_id,
            "room": payload["room"],
            "language": payload["language"],
            "native_language": payload["native_language"],
            "started_at": _to_sql_datetime(started_at),
            "ended_at": _to_sql_datetime(ended_at),
            "turn_count": len(transcript),
            "langfuse_trace_url": trace_url,
            "blob_path": blob_name,
        })

        processed += 1
        if latest_timestamp is None or started_at > latest_timestamp:
            latest_timestamp = started_at

    if latest_timestamp:
        set_last_run_until(conn, _to_sql_datetime(latest_timestamp))

    conn.close()
    _log(f"done — processed {processed} session(s)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        _log(f"FAILED: {exc}")
        sys.exit(1)
