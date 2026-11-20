import asyncio
from unittest.mock import AsyncMock

import pytest

from src.meta import Meta
from src.trackers.UNIT3D.skipthecommercials import SkipTheCommercials


@pytest.fixture
def tracker() -> SkipTheCommercials:
    stc = SkipTheCommercials({"DEFAULT": {}, "TRACKERS": {"SKIPTHECOMMERCIALS": {}}})
    stc.common.check_language_requirements = AsyncMock(return_value=True)
    return stc


@pytest.mark.parametrize(
    "meta",
    [
        Meta(category="TV", valid_mi_settings=True),
        Meta(category="MOVIE", genres=["Documentary"], valid_mi_settings=True),
        Meta(category="MOVIE", keywords=["documentary"], valid_mi_settings=True),
        Meta(category="MOVIE", combined_genres="History, Documentary", valid_mi_settings=True),
        Meta(category="MOVIE", combined_genres=["Documentaries"], valid_mi_settings=True),
    ],
)
def test_skipthecommercials_allows_tv_and_documentary_movies(tracker: SkipTheCommercials, meta: Meta) -> None:
    assert asyncio.run(tracker.get_additional_checks(meta)) is True  # noqa: S101


@pytest.mark.parametrize(
    "meta",
    [
        Meta(category="MOVIE", genres=["Action", "Drama"], unattended=True),
        Meta(category="MOVIE", keywords=["documentary filmmaker"], unattended=True),
        Meta(category="MUSIC", genres=["Documentary"], unattended=True),
    ],
)
def test_skipthecommercials_rejects_non_documentary_movies_and_other_categories(tracker: SkipTheCommercials, meta: Meta) -> None:
    assert asyncio.run(tracker.get_additional_checks(meta)) is False  # noqa: S101


@pytest.mark.parametrize(
    "meta",
    [
        Meta(category="TV", combined_genres=["Porn"], unattended=True),
        Meta(category="TV", keywords=["porn"], unattended=True),
        Meta(category="MOVIE", combined_genres=["Documentary", "Porn"], unattended=True),
    ],
)
def test_skipthecommercials_rejects_adult_list_metadata(tracker: SkipTheCommercials, meta: Meta) -> None:
    assert asyncio.run(tracker.get_additional_checks(meta)) is False  # noqa: S101


def test_skipthecommercials_rejects_missing_encoding_settings(tracker: SkipTheCommercials) -> None:
    assert asyncio.run(tracker.get_additional_checks(Meta(category="TV", valid_mi_settings=False))) is False  # noqa: S101


def test_skipthecommercials_rejects_failed_english_requirement(tracker: SkipTheCommercials) -> None:
    tracker.common.check_language_requirements = AsyncMock(return_value=False)

    assert asyncio.run(tracker.get_additional_checks(Meta(category="TV", valid_mi_settings=True))) is False  # noqa: S101


def test_skipthecommercials_full_discs_skip_english_requirement(tracker: SkipTheCommercials) -> None:
    tracker.common.check_language_requirements = AsyncMock(return_value=False)

    assert asyncio.run(tracker.get_additional_checks(Meta(category="TV", is_disc="BDMV", valid_mi_settings=True))) is True  # noqa: S101


def test_skipthecommercials_bans_listed_groups(tracker: SkipTheCommercials) -> None:
    assert "seedpool" in tracker.banned_groups  # noqa: S101
    assert "YTS" in tracker.banned_groups  # noqa: S101


def _tv_meta(**overrides: object) -> Meta:
    fields: dict[str, object] = {
        "category": "TV",
        "type": "HDTV",
        "title": "Show",
        "season": "S01",
        "resolution": "720p",
        "source": "HDTV",
        "audio": "AAC 2.0",
        "video_encode": "H.264",
        "audio_languages": ["English"],
        "language_checked": True,
    }
    fields.update(overrides)
    return Meta(**fields)


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        (_tv_meta(tag="-GRP"), "Show S01 720p HDTV AAC 2.0 H.264-GRP"),
        (_tv_meta(), "Show S01 720p HDTV AAC 2.0 H.264-NOGROUP"),
        (_tv_meta(audio_languages=["French"]), "Show S01 720p HDTV FRENCH AAC 2.0 H.264-NOGROUP"),
        (_tv_meta(manual_name="Show S01 Custom"), "Show S01 Custom"),
    ],
)
def test_skipthecommercials_name_adds_nogroup(tracker: SkipTheCommercials, meta: Meta, expected: str) -> None:
    assert asyncio.run(tracker.get_name(meta)) == {"name": expected}  # noqa: S101
