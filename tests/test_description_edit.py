# ruff: noqa: S101

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import click
import pytest

import src.description_review as description_review
import src.get_tracker_data as get_tracker_data
from src.description_review import edit_description, load_review
from src.get_tracker_data import TrackerDataManager
from src.meta import Meta
from web_ui import server


def _meta(tmp_path: Path, **values: object) -> Meta:
    return Meta(base_dir=str(tmp_path), uuid="edit-test", **values)


def _review(tmp_path: Path) -> dict[str, object]:
    return load_review(tmp_path / "tmp" / "edit-test")


def _editor_must_not_run(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("a terminal editor must not be opened")


def test_webui_child_environment_routes_description_edits_to_the_panel():
    assert server._webui_subprocess_env()["UA_WEBUI_ACTIVE"] == "1"


def test_webui_edit_stages_each_request_as_a_new_draft_version(tmp_path, monkeypatch):
    monkeypatch.setenv("UA_WEBUI_ACTIVE", "1")
    monkeypatch.setattr(description_review.click, "edit", _editor_must_not_run)
    meta = _meta(tmp_path)

    assert asyncio.run(edit_description(meta, "first", "AITHER")) is None
    assert _review(tmp_path) == {"content": "first", "version": 1}

    assert asyncio.run(edit_description(meta, "second", "HDBITS")) is None
    assert _review(tmp_path) == {"content": "second", "version": 2}


def test_terminal_edit_returns_the_edited_text(tmp_path, monkeypatch):
    monkeypatch.delenv("UA_WEBUI_ACTIVE", raising=False)
    monkeypatch.setattr(description_review.click, "edit", lambda text: f"{text} edited")

    assert asyncio.run(edit_description(_meta(tmp_path), "notes", "AITHER")) == "notes edited"
    assert _review(tmp_path) == {}


@pytest.mark.parametrize("error", [click.ClickException("sensible-editor: Editing failed"), OSError("no editor")])
def test_editor_failure_keeps_the_description_instead_of_aborting(tmp_path, monkeypatch, error):
    monkeypatch.delenv("UA_WEBUI_ACTIVE", raising=False)

    def fail(_text: str) -> None:
        raise error

    monkeypatch.setattr(description_review.click, "edit", fail)

    assert asyncio.run(edit_description(_meta(tmp_path), "notes", "AITHER")) is None


def test_webui_tracker_description_goes_to_the_panel_without_a_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("UA_WEBUI_ACTIVE", "1")
    monkeypatch.setattr(get_tracker_data, "prompt_in_thread", AsyncMock(side_effect=AssertionError("no prompt in the WebUI")))
    meta = _meta(tmp_path)
    candidate = Meta(base_dir=str(tmp_path), uuid="isolated-candidate", description="Deleted scenes notes")

    asyncio.run(TrackerDataManager({"DEFAULT": {}, "TRACKERS": {}})._review_explicit_tracker_description(meta, "AITHER", candidate))

    # The draft belongs to the upload, not to the isolated candidate worker.
    assert _review(tmp_path) == {"content": "Deleted scenes notes", "version": 1}
    assert not (tmp_path / "tmp" / "isolated-candidate").exists()


def test_webui_tracker_description_keeps_a_draft_the_user_already_edited(tmp_path, monkeypatch):
    monkeypatch.setenv("UA_WEBUI_ACTIVE", "1")
    meta = _meta(tmp_path)
    description_review.save_review(tmp_path / "tmp" / "edit-test", "my edit", 3)
    candidate = Meta(base_dir=str(tmp_path), uuid="isolated-candidate", description="Second tracker text")

    asyncio.run(TrackerDataManager({"DEFAULT": {}, "TRACKERS": {}})._review_explicit_tracker_description(meta, "BLUTOPIA", candidate))

    assert _review(tmp_path) == {"content": "my edit", "version": 3}


def test_cli_tracker_description_survives_a_failed_editor(tmp_path, monkeypatch):
    monkeypatch.delenv("UA_WEBUI_ACTIVE", raising=False)
    monkeypatch.setattr(get_tracker_data, "prompt_in_thread", AsyncMock(return_value="e"))

    def fail(_text: str) -> None:
        raise click.ClickException("sensible-editor: Editing failed")

    monkeypatch.setattr(description_review.click, "edit", fail)
    meta = _meta(tmp_path)
    candidate = Meta(base_dir=str(tmp_path), uuid="isolated-candidate", description="Deleted scenes notes")

    asyncio.run(TrackerDataManager({"DEFAULT": {}, "TRACKERS": {}})._review_explicit_tracker_description(meta, "AITHER", candidate))

    assert candidate.description == "Deleted scenes notes"
