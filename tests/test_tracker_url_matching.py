"""Torrents already in the client are matched to trackers by their announce URL."""

import asyncio

import pytest

from src.meta import Meta
from src.torrent_clients import qbittorrent


@pytest.fixture(autouse=True)
def fresh_pattern_cache(monkeypatch):
    monkeypatch.setattr(qbittorrent, "_cached_tracker_url_patterns", None)


def matched(*announce_urls: str) -> list[str]:
    meta = Meta()
    asyncio.run(qbittorrent.match_tracker_url(list(announce_urls), meta))
    return sorted(meta.remove_trackers)


@pytest.mark.parametrize(
    ("announce", "tracker"),
    [
        ("https://torrenthaven.org/announce/abc123", "TORRENTHAVEN"),
        ("https://hellenic-hd.cc/announce/abc123", "HELLENICHD"),
        ("https://0dayfiles.net/announce/abc123", "0DAYFILES"),
    ],
)
def test_tracker_without_tracker_urls_matches_on_its_base_url(announce, tracker):
    assert matched(announce) == [tracker]


def test_explicit_tracker_urls_still_match():
    assert matched("https://znth.cx/announce/abc123") == ["ZENITH"]


def test_unknown_announce_matches_nothing():
    assert matched("https://tracker.example.org/announce/abc123") == []
