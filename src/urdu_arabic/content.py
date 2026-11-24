"""Lesson content loader.

Reads the generated lecture JSON files produced by
src/content/generate_concept_slides.py (src/urdu_arabic/content_data/) --
one file per lecture, each lecture broken into small concept "parts" with
synced-audio Urdu narration and a comprehension question. See that
module's docstring for how content is authored and generated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .languages import DEFAULT_LANGUAGE

CONTENT_DATA_DIR = Path(__file__).resolve().parent / "content_data"


def _load_all_lessons() -> dict[str, dict[str, Any]]:
    # Not cached: content is generated/added incrementally (overnight, in
    # this build) and this directory is small (tens of files) -- re-reading
    # it per request is cheap and means a new lecture shows up without
    # restarting the server.
    lessons: dict[str, dict[str, Any]] = {}
    if not CONTENT_DATA_DIR.exists():
        return lessons
    for path in sorted(CONTENT_DATA_DIR.glob("lecture-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        lessons[data["id"]] = data
    return lessons


def list_lessons() -> list[dict[str, Any]]:
    """Summary list for the lesson picker: id, title, part count, and a
    lightweight list of part titles so the UI can show a foldable list of
    sub-concepts without a second request per lesson."""
    return [
        {
            "id": lesson["id"],
            "title": lesson["title"],
            "part_count": len(lesson["parts"]),
            "parts": [
                {"id": part["id"], "title": part["title"]}
                for part in lesson["parts"]
            ],
        }
        for lesson in _load_all_lessons().values()
    ]


def get_lesson(lesson_id: str) -> dict[str, Any] | None:
    return _load_all_lessons().get(lesson_id)


def get_part(lesson_id: str, part_id: str) -> dict[str, Any] | None:
    lesson = get_lesson(lesson_id)
    if lesson is None:
        return None
    for part in lesson["parts"]:
        if part["id"] == part_id:
            return part
    return None


def get_part_context(lesson_id: str, part_id: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Short text describing the current lesson part, to ground the LLM's answer."""
    lesson = get_lesson(lesson_id)
    part = get_part(lesson_id, part_id)
    if lesson is None or part is None:
        return ""
    narration_lang = part["narration"].get(language) or part["narration"][DEFAULT_LANGUAGE]
    narration = " ".join(s["text"] for s in narration_lang["sentences"])
    example = f" The Arabic example taught is '{part['arabic_example']}'." if part.get("arabic_example") else ""
    lesson_title = lesson["title"].get(language, lesson["title"][DEFAULT_LANGUAGE])
    part_title = part["title"].get(language, part["title"][DEFAULT_LANGUAGE])
    return (
        f"Lesson: {lesson_title}. Current concept: {part_title}.{example} "
        f"Explained as: {narration}"
    )
