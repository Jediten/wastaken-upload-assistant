# ruff: noqa: S101
"""Chevereto hosts make no medium rendition for images at or under 500 px, so the full image URL must be used."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.uploadscreens import upload_image_task


def _upload(tmp_path: Path, host: str, config_key: str, payload: object) -> dict:
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"image data")
    response = httpx.Response(200, content=json.dumps(payload), request=httpx.Request("POST", "https://example.invalid/api/1/upload"))
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    with patch("src.uploadscreens.httpx.AsyncClient", return_value=client):
        return asyncio.run(upload_image_task((str(image), host, {"DEFAULT": {config_key: "test-key"}}, None)))


_FULL = "https://img.example.invalid/cover.jpg"
_MEDIUM = "https://img.example.invalid/cover.md.jpg"
_VIEWER = "https://example.invalid/image/cover"


@pytest.mark.parametrize(("host", "config_key"), [("ptscreens", "ptscreens_api"), ("utppm", "utppm_api")])
def test_small_cover_without_medium_uses_full_image_url(tmp_path: Path, host: str, config_key: str) -> None:
    result = _upload(tmp_path, host, config_key, {"status_code": 200, "image": {"url": _FULL, "url_viewer": _VIEWER}})
    assert result["status"] == "success"
    assert result["img_url"] == _FULL
    assert result["raw_url"] == _FULL
    assert result["web_url"] == _VIEWER


def test_onlyimage_small_cover_without_medium_uses_full_image_url(tmp_path: Path) -> None:
    result = _upload(tmp_path, "onlyimage", "onlyimage_api", {"success": True, "data": {"url": _FULL, "url_viewer": _VIEWER, "image": {"url": _FULL}}})
    assert result["status"] == "success"
    assert result["img_url"] == _FULL
    assert result["raw_url"] == _FULL


def test_large_image_still_prefers_medium(tmp_path: Path) -> None:
    result = _upload(tmp_path, "ptscreens", "ptscreens_api", {"status_code": 200, "image": {"url": _FULL, "url_viewer": _VIEWER, "medium": {"url": _MEDIUM}}})
    assert result["status"] == "success"
    assert result["img_url"] == _MEDIUM
    assert result["raw_url"] == _FULL


def test_empty_medium_url_falls_back_to_full_image_url(tmp_path: Path) -> None:
    result = _upload(tmp_path, "ptscreens", "ptscreens_api", {"status_code": 200, "image": {"url": _FULL, "url_viewer": _VIEWER, "medium": {"url": None}}})
    assert result["status"] == "success"
    assert result["img_url"] == _FULL
