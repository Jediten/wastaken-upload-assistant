"""Regression tests for BeyondHD encode codec checks."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.meta import Meta
from src.trackers.beyondhd import BEYONDHD


def _check(video_encode: str, uhd: str = "") -> tuple[bool, list[str]]:
    """Run the checks and return the result plus every failure reason they logged.

    Checks only explain failures; the "upload anyway?" question is asked once by
    TrackerStatusManager, so there is no per-check prompt to capture.
    """
    tracker = BEYONDHD({"DEFAULT": {}, "TRACKERS": {"BEYONDHD": {}}})
    messages: list[str] = []

    meta = Meta(
        type="ENCODE",
        container="mkv",
        valid_mi_settings=True,
        video_encode=video_encode,
        audio="Opus 2.0",
        uhd=uhd,
        tag="-Example",
    )
    with (
        patch.object(tracker, "get_name", AsyncMock(return_value="Fictional Movie 2001 1080p BluRay Opus 2.0 x264-Example")),
        patch("src.trackers.beyondhd.logger.info", side_effect=lambda message, *_args, **_kwargs: messages.append(str(message))),
        patch("src.trackers.beyondhd.Common.check_and_confirm_adult_media_upload", return_value=True),
    ):
        result = asyncio.run(tracker.get_additional_checks(meta))
    return result, messages


@pytest.mark.parametrize("video_encode", [" x264", "Hi10P x264", "x264"])
def test_beyondhd_accepts_x264_encode_with_profile_prefix(video_encode):
    assert _check(video_encode) == (True, [])


def test_beyondhd_rejects_non_x26x_encode():
    result, messages = _check(" H.264")
    assert result is False
    assert any("Encodes must use x264 or x265" in message for message in messages)


def test_beyondhd_rejects_non_uhd_x265_encode():
    result, messages = _check(" x265")
    assert result is False
    assert any("x265 encodes" in message for message in messages)
    assert _check(" x265", uhd="UHD") == (True, [])
