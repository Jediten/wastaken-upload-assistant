"""Hellenic-HD splits movies and series by whether Greek subtitles are present."""

# ruff: noqa: S101

import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.hellenichd import HellenicHD


def category_id(**fields) -> str:
    meta = Meta(language_checked=True, **fields)
    return asyncio.run(HellenicHD({"TRACKERS": {"HELLENICHD": {}}}).get_category_id(meta))["category_id"]


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"category": "MOVIE", "subtitle_languages": ["Greek"]}, "1"),
        ({"category": "TV", "subtitle_languages": ["English", "Greek (SDH)"]}, "2"),
        ({"category": "MOVIE", "subtitle_languages": ["English"]}, "20"),
        ({"category": "TV", "subtitle_languages": []}, "21"),
        ({"category": "MOVIE", "subtitle_languages": [], "subtitle_files": ["/media/Movie.2020.el.srt"]}, "1"),
        ({"category": "TV", "subtitle_languages": [], "subtitle_files": ["/media/Show.S01E01.en.srt"]}, "21"),
        ({"category": "TV", "is_sports": True, "subtitle_languages": []}, "14"),
    ],
)
def test_category_follows_greek_subtitles(fields, expected):
    assert category_id(**fields) == expected


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({"category": "MOVIE", "resolution": "1080p", "subtitle_languages": ["English"]}, True),
        ({"category": "TV", "resolution": "720p", "subtitle_languages": [], "subtitle_files": ["/media/Show.S01E01.el.srt"]}, True),
        ({"category": "MOVIE", "resolution": "576p", "subtitle_languages": ["Greek"]}, False),
        ({"category": "MOVIE", "resolution": "2160p", "subtitle_languages": []}, False),
    ],
)
def test_additional_checks_enforce_resolution_and_subtitles(fields, expected):
    meta = Meta(language_checked=True, **fields)
    assert asyncio.run(HellenicHD({"TRACKERS": {"HELLENICHD": {}}}).get_additional_checks(meta)) is expected


def test_reverse_mapping_round_trips():
    tracker = HellenicHD({"TRACKERS": {"HELLENICHD": {}}})
    mapping = asyncio.run(tracker.get_category_id(Meta(), mapping_only=True))
    assert asyncio.run(tracker.get_category_id(Meta(), reverse=True)) == {v: k for k, v in mapping.items()}
