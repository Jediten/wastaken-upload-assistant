"""Regression tests for 0DayFiles' scene-style categories."""

import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.zerodayfiles import ZeroDayFiles


def tracker() -> ZeroDayFiles:
    return ZeroDayFiles({"DEFAULT": {}, "TRACKERS": {"0DAYFILES": {}}})


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"category": "MOVIE", "is_disc": "BDMV", "resolution": "2160p"}, "12"),
        ({"category": "MOVIE", "is_disc": "DVD", "resolution": "480p", "sd": 1}, "14"),
        ({"category": "MOVIE", "type": "WEBDL", "resolution": "2160p", "video_encode": "H.265"}, "10"),
        ({"category": "MOVIE", "type": "ENCODE", "resolution": "576p", "sd": 1, "video_encode": "x264"}, "9"),
        ({"category": "MOVIE", "type": "WEBDL", "resolution": "1080p", "video_encode": "H.264"}, "58"),
        ({"category": "MOVIE", "type": "ENCODE", "resolution": "1080p", "video_encode": "x265", "video_codec": "HEVC"}, "19"),
        ({"category": "MOVIE", "type": "ENCODE", "resolution": "1080p", "video_encode": "x264", "video_codec": "AVC"}, "11"),
        ({"category": "MOVIE", "type": "REMUX", "resolution": "1080p", "video_codec": "AVC"}, "11"),
        ({"category": "MOVIE", "type": "HDTV", "resolution": "720p", "video_encode": "x264", "video_codec": "AVC"}, "18"),
        ({"category": "TV", "is_disc": "BDMV", "resolution": "1080p"}, "23"),
        ({"category": "TV", "type": "DVDRIP", "resolution": "480p", "sd": 1, "video_encode": "XviD"}, "25"),
        ({"category": "TV", "type": "HDTV", "resolution": "480p", "sd": 1}, "21"),
        ({"category": "TV", "type": "WEBRIP", "resolution": "1080p", "video_encode": "x265"}, "59"),
        ({"category": "TV", "type": "HDTV", "resolution": "1080p", "video_encode": "x265", "video_codec": "HEVC"}, "31"),
        ({"category": "TV", "type": "HDTV", "resolution": "720p", "video_encode": "x264", "video_codec": "AVC"}, "30"),
        ({"category": "TV", "type": "WEBDL", "resolution": "1080p", "anime": True}, "43"),
    ],
)
def test_category_follows_the_release(fields, expected):
    assert asyncio.run(tracker().get_category_id(Meta(**fields)))["category_id"] == expected


def test_name_drops_banned_characters_but_keeps_dts_x():
    meta = Meta(category="MOVIE", name="Mission: Impossible 1996 1080p BluRay DTS:X 7.1 x264-GROUP")

    assert asyncio.run(tracker().get_name(meta))["name"] == "Mission Impossible 1996 1080p BluRay DTS:X 7.1 x264-GROUP"


def test_dupe_search_does_not_filter_on_type_or_resolution():
    params = [("tmdbId", "603"), ("resolutions[]", "3"), ("types[]", "3"), ("name", "")]

    urls = asyncio.run(tracker().get_search_urls(Meta(category="MOVIE"), params))

    assert urls[0][1] == [("tmdbId", "603"), ("name", "")]


def test_held_dupe_is_reported_as_waiting_for_staff():
    held = {"success": True, "message": "Torrent uploaded", "status": "held_for_moderation", "reason": "possible_dupe"}

    message = asyncio.run(tracker().process_response_data(held))

    assert "held for staff review" in message


def test_mod_queue_opt_in_follows_config():
    configured = ZeroDayFiles({"DEFAULT": {}, "TRACKERS": {"0DAYFILES": {"modq": True}}})

    assert asyncio.run(configured.get_additional_data(Meta(category="MOVIE"))) == {"mod_queue_opt_in": "1"}
