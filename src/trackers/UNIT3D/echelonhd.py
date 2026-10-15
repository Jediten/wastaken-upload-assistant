# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]

# EchelonHD is a custom site with a UNIT3D-compatible API. Only send what its
# own upload form has; UNIT3D's staff flags (featured, free, sticky, ...) are
# not part of it. Type and resolution IDs match the UNIT3D defaults.
_UPLOAD_FIELDS = frozenset(
    {
        "name",
        "category_id",
        "type_id",
        "resolution_id",
        "tmdb",
        "imdb",
        "tvdb",
        "mal",
        "igdb",
        "season_number",
        "episode_number",
        "distributor_id",
        "region_id",
        "description",
        "mediainfo",
        "bdinfo",
        "keywords",
        "anonymous",
        "personal_release",
    }
)


class EchelonHD(UNIT3D):
    """
    EchelonHD (EHD) — private tracker with a UNIT3D-compatible API.
    """

    tracker = "ECHELONHD"
    display_name = "EchelonHD"
    base_url = "https://echelonhd.me"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    tracker_urls = ("echelonhd.me",)
    supported_categories = ("MOVIE", "TV")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="ECHELONHD")
        self.config = config
        self.common = Common(config)

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "ANIME": "6",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}
        resolved = category or meta.category or ""
        if meta.anime and resolved in ("MOVIE", "TV"):
            resolved = "ANIME"
        return {"category_id": category_id.get(resolved, "0")}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        # Site rule: name the release the way its group named it. Use the scene or
        # file/folder name when it carries the detected group tag; a folder the user
        # renamed has no group name to keep, so it gets the generated name instead.
        original = (meta.scene_name or meta.basename_no_ext or "").strip()
        tag = (meta.tag or "").strip()
        if original and tag and original.casefold().endswith(tag.casefold()):
            return {"name": original}
        return await super().get_name(meta)

    async def get_data(self, meta: Meta) -> dict[str, str]:
        data = await super().get_data(meta)
        return {key: value for key, value in data.items() if key in _UPLOAD_FIELDS}
