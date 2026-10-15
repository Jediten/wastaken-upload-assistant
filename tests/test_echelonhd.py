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
