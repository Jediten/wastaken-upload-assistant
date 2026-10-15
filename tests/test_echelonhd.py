"""EchelonHD speaks the UNIT3D API but is not UNIT3D: its own IDs and form fields apply."""

import asyncio

import pytest

from src.meta import Meta
from src.trackers.UNIT3D import UNIT3D
from src.trackers.UNIT3D.echelonhd import EchelonHD


def tracker(**options) -> EchelonHD:
    return EchelonHD({"DEFAULT": {}, "TRACKERS": {"ECHELONHD": options}})


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"category": "MOVIE"}, "1"),
        ({"category": "TV"}, "2"),
        ({"category": "TV", "anime": True}, "6"),
        ({"category": "MOVIE", "anime": True}, "6"),
    ],
)
def test_category_ids(fields, expected):
    assert asyncio.run(tracker().get_category_id(Meta(**fields)))["category_id"] == expected


def test_upload_sends_only_the_fields_of_the_sites_own_form(monkeypatch):
    async def stock_data(_self, _meta):
        return {
            "name": "Example 2020 1080p BluRay x264-GRP",
            "category_id": "1",
            "type_id": "3",
            "resolution_id": "3",
            "anonymous": "0",
            "featured": "1",
            "free": "100",
            "doubleup": "1",
            "sticky": "1",
            "internal": "0",
            "stream": "0",
            "sd": "0",
            "exclusive": "1",
            "mod_queue_opt_in": "0",
        }

    monkeypatch.setattr(UNIT3D, "get_data", stock_data)

    data = asyncio.run(tracker(featured=True, free=True).get_data(Meta(category="MOVIE")))

    assert data == {
        "name": "Example 2020 1080p BluRay x264-GRP",
        "category_id": "1",
        "type_id": "3",
        "resolution_id": "3",
        "anonymous": "0",
    }


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {"basename_no_ext": "The.Act.S01.BluRay.1080p.DTS-HD.MA.5.1.AVC.REMUX-FraMeSToR", "tag": "-FraMeSToR"},
            "The Act S01 BluRay 1080p DTS-HD MA 5.1 AVC REMUX-FraMeSToR",
        ),
        (
            {"scene_name": "Example.Show.S01E01.720p.HDTV.x264-SCENE", "basename_no_ext": "example.show.s01e01", "tag": "-SCENE"},
            "Example Show S01E01 720p HDTV x264-SCENE",
        ),
        (
            {"basename_no_ext": "American.Psycho.2000.Unrated.PROPER.BluRay.1080p.TrueHD.Atmos.7.1.AVC.HYBRID.REMUX-FraMeSToR", "tag": "-FraMeSToR"},
            "American Psycho 2000 Unrated PROPER BluRay 1080p TrueHD Atmos 7.1 AVC HYBRID REMUX-FraMeSToR",
        ),
        (
            {"basename_no_ext": "Blade.Runner.2049.2017.2160p.AMZN.WEB-DL.DDP5.1.H.265-GROUP", "tag": "-GROUP"},
            "Blade Runner 2049 2017 2160p AMZN WEB-DL DDP5.1 H.265-GROUP",
        ),
        (
            {"basename_no_ext": "My hero Academia S02 BDREMUX", "tag": "-ZR"},
            "My Hero Academia S02 1080p BluRay REMUX AVC TrueHD 5.1-ZR",
        ),
    ],
)
def test_name_keeps_the_group_release_name(fields, expected):
    meta = Meta(category="TV", name="My Hero Academia S02 1080p BluRay REMUX AVC TrueHD 5.1-ZR", **fields)

    assert asyncio.run(tracker().get_name(meta))["name"] == expected
