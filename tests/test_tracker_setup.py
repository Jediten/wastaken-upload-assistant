# ruff: noqa: S101

import json
from typing import Any

import pytest

from src.meta import Meta
from src.trackersetup import TrackerSetup


def test_music_trackers_are_filtered_before_tracker_specific_work():
    meta = Meta(category="MUSIC", trackers=["HDBITS", "ORPHEUS", "AITHER"])
    setup = TrackerSetup(
        {
            "TRACKERS": {
                "HDBITS": {"announce_url": "https://hdbits.example/announce"},
                "ORPHEUS": {"api_key": "token", "announce_url": "https://orpheus.example/announce"},
                "AITHER": {"api_key": "token"},
            }
        }
    )

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["ORPHEUS"]
    assert meta.tracker_status["HDBITS"] == {"upload": False, "skipped": True}
    assert meta.tracker_status["AITHER"] == {"upload": False, "skipped": True}


def test_cathoderaytube_is_registered_for_supported_categories():
    meta = Meta(category="GAME", trackers=["CATHODERAYTUBE"])
    setup = TrackerSetup({"TRACKERS": {"CATHODERAYTUBE": {"announce_url": "https://signal.cathode-ray.tube/passkey/announce"}}})

    setup.filter_unsupported_trackers(meta)

    assert meta.trackers == ["CATHODERAYTUBE"]


class _BannedGroupsResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {"count": 2, "groups": [{"name": "BannedGroup", "reason": "Rule"}, {"name": "AnotherGroup", "reason": "Rule"}], "updated_at": "2026-08-04"}


class _BannedGroupsClient:
    def __init__(self, requests: list[dict[str, Any]]) -> None:
        self.requests = requests

    async def __aenter__(self) -> _BannedGroupsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, **kwargs: Any) -> _BannedGroupsResponse:
        self.requests.append(kwargs)
        return _BannedGroupsResponse()


@pytest.mark.asyncio
async def test_capybarabr_fetches_banned_groups_with_api_token(tmp_path, monkeypatch: pytest.MonkeyPatch):
    requests: list[dict[str, Any]] = []
    monkeypatch.setattr("src.trackersetup.httpx.AsyncClient", lambda: _BannedGroupsClient(requests))
    setup = TrackerSetup({"TRACKERS": {"CAPYBARABR": {"api_key": "test-token"}}})

    file_path = await setup.get_banned_groups(Meta(base_dir=str(tmp_path)), "CAPYBARABR")

    assert requests == [
        {
            "url": "https://capybarabr.com/api/banned-groups",
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "params": {"api_token": "test-token"},
        }
    ]
    assert file_path == tmp_path / "data" / "banned" / "CAPYBARABR_banned_groups.json"
    assert json.loads(file_path.read_text(encoding="utf-8"))["banned_groups"] == "BannedGroup, AnotherGroup"


class _InfinityHDBannedGroupsResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "data": [
                {"name": "YIFY", "all_types": True, "types": [], "type_ids": [], "reason": "Quality."},
                {"name": "EVO", "all_types": False, "types": ["Full Disc", "Remux", "Encode", "WEBRip", "HDTV"], "type_ids": [1, 2, 3, 5, 6], "reason": "Quality."},
            ],
            "meta": {"count": 2, "wiki": "https://infinityhd.net/wikis/5"},
        }


class _InfinityHDBannedGroupsClient(_BannedGroupsClient):
    async def get(self, **kwargs: Any) -> _InfinityHDBannedGroupsResponse:  # type: ignore[override]
        self.requests.append(kwargs)
        return _InfinityHDBannedGroupsResponse()


@pytest.mark.asyncio
async def test_infinityhd_fetches_banned_groups_with_bearer_token(tmp_path, monkeypatch: pytest.MonkeyPatch):
    requests: list[dict[str, Any]] = []
    monkeypatch.setattr("src.trackersetup.httpx.AsyncClient", lambda: _InfinityHDBannedGroupsClient(requests))
    monkeypatch.setattr("src.trackersetup.observe_tracker_response", lambda *_: None)
    setup = TrackerSetup({"TRACKERS": {"INFINITYHD": {"api_key": "test-token"}}})

    file_path = await setup.get_banned_groups(Meta(base_dir=str(tmp_path)), "INFINITYHD")

    assert len(requests) == 1
    assert requests[0]["url"] == "https://infinityhd.net/api/banned-groups"
    assert requests[0]["headers"]["Authorization"] == "Bearer test-token"
    assert file_path == tmp_path / "data" / "banned" / "INFINITYHD_banned_groups.json"
    assert json.loads(file_path.read_text(encoding="utf-8"))["banned_groups"] == "YIFY, EVO"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tag", "release_type", "banned"),
    [
        ("-EVO", "WEBDL", False),
        ("-EVO", "ENCODE", True),
        ("-evo", "REMUX", True),
        ("-EVO", None, True),
        ("-YIFY", "WEBDL", True),
        ("-GOOD", "ENCODE", False),
    ],
)
async def test_infinityhd_banned_groups_follow_the_release_type(tmp_path, monkeypatch: pytest.MonkeyPatch, tag: str, release_type: str | None, banned: bool):
    requests: list[dict[str, Any]] = []
    monkeypatch.setattr("src.trackersetup.httpx.AsyncClient", lambda: _InfinityHDBannedGroupsClient(requests))
    monkeypatch.setattr("src.trackersetup.observe_tracker_response", lambda *_: None)
    setup = TrackerSetup({"TRACKERS": {"INFINITYHD": {"api_key": "test-token"}}})
    meta = Meta(base_dir=str(tmp_path), tag=tag, type=release_type, unattended=True)

    # The bundled list bans EVO outright; the API's type scope must win over it.
    assert await setup.check_banned_group("INFINITYHD", ["EVO"], meta) is banned


@pytest.mark.asyncio
@pytest.mark.parametrize(("answer", "banned"), [(True, False), (False, True)])
async def test_banned_group_override_asks_through_the_shared_prompt(answer: bool, banned: bool):
    questions: list[str] = []

    async def prompt_yes_no(question: str, default: bool = False) -> bool:
        assert default is False
        questions.append(question)
        return answer

    meta = Meta(tag="-ZR", unattended=False)

    assert await TrackerSetup({}).check_banned_group("SKIPTHECOMMERCIALS", ["ZR"], meta, prompt_yes_no=prompt_yes_no) is banned
    assert questions == ["SKIPTHECOMMERCIALS: ZR is a banned group. Do you want to continue anyway?"]
