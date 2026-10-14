"""Persistent, execution-scoped description drafts for CLI and WebUI review."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import click

from src.console import logger

_REVIEW_FILE = "description_review.json"


def review_path(temp_dir: Path) -> Path:
    return temp_dir / _REVIEW_FILE


def load_review(temp_dir: Path) -> dict[str, Any]:
    try:
        value = json.loads(review_path(temp_dir).read_text(encoding="utf-8"))
    except OSError, ValueError, TypeError:
        return {}
    return value if isinstance(value, dict) else {}


def save_review(temp_dir: Path, content: str, version: int) -> dict[str, Any]:
    """Atomically persist a user draft without relying on a browser path."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    payload = {"content": content, "version": version}
    path = review_path(temp_dir)
    temporary = path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return payload


def source_items(meta: dict[str, Any]) -> list[dict[str, str]]:
    """Return inspectable read-only inputs used to build the base description."""
    items: list[dict[str, str]] = []
    for key, label in (
        ("description", "Tracker description"),
        ("description_link_content", "Description link"),
        ("description_file_content", "Description file"),
        ("description_template_content", "Template"),
        ("description_nfo_content", "NFO"),
    ):
        content = meta.get(key)
        if isinstance(content, str) and content.strip():
            items.append({"key": key, "label": label, "content": content})
    return items


def draft(meta: dict[str, Any], temp_dir: Path) -> tuple[str, int]:
    review = load_review(temp_dir)
    content = review.get("content")
    if isinstance(content, str):
        try:
            version = int(review.get("version", 0) or 0)
        except TypeError, ValueError:
            version = 0
        return content, version
    override = meta.get("description_override")
    if isinstance(override, str) and override:
        return override, 0
    items = source_items(meta)
    return (items[0]["content"] if items else ""), 0


def webui_review_active() -> bool:
    """Return whether this run is a WebUI child, which edits through the Description panel."""
    return os.environ.get("UA_WEBUI_ACTIVE") == "1"


def stage_draft(meta: Any, content: str, *, keep_existing: bool = False) -> None:
    """Load ``content`` into the WebUI Description panel as the next draft version."""
    temp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
    review = load_review(temp_dir)
    if keep_existing and isinstance(review.get("content"), str):
        return
    try:
        version = int(review.get("version", 0) or 0) + 1
    except TypeError, ValueError:
        version = 1
    save_review(temp_dir, content, version)


async def edit_description(meta: Any, text: str, source: str) -> str | None:
    """Let the user edit a grabbed description; ``None`` means keep ``text`` unchanged.

    WebUI runs have no terminal, so the text goes to the Description panel instead
    of an editor. A terminal editor that cannot start never aborts the upload.
    """
    if webui_review_active():
        await asyncio.to_thread(stage_draft, meta, text)
        logger.info(f"[cyan]Description from {source} loaded into the Description panel; edit it there before confirming the upload.[/cyan]")
        return None
    try:
        edited = await asyncio.to_thread(click.edit, text)
    except (click.ClickException, OSError) as error:
        logger.warning(f"[yellow]Could not open an editor ({error}); keeping the {source} description unchanged.[/yellow]")
        return None
    return None if edited is None else str(edited)


def apply_saved_draft(meta: Any) -> None:
    """Synchronize a saved WebUI draft into the live Meta object at use time."""
    temp_dir = Path(meta.base_dir) / "tmp" / meta.uuid
    review = load_review(temp_dir)
    content = review.get("content")
    if isinstance(content, str):
        meta.description_override = content
        # Several tracker adapters use ``meta.description`` directly. Keep both
        # views synchronized so a WebUI edit
        # is honored by every tracker-specific description builder.
        meta.description = content
        meta.saved_description = bool(content)


def get_base_description(meta: Any) -> str:
    """Return the one authoritative base description for an upload."""
    apply_saved_draft(meta)
    description = getattr(meta, "description", "") or ""
    return description if isinstance(description, str) else str(description)
