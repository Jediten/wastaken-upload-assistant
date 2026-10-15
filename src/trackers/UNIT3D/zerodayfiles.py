# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D, ParamsList

Config = dict[str, Any]

# 0DayFiles has no type or resolution fields; the category carries both
# (Movies/4K, Movies/x264, TV/WEB, ...). IDs read from the site's upload form.
CATEGORY_IDS = {
    "MOVIE_480P": "9",
    "MOVIE_4K": "10",
    "MOVIE_BLURAY": "11",
    "MOVIE_BLURAY_FULL": "12",
    "MOVIE_DVDR": "14",
    "MOVIE_X264": "18",
    "MOVIE_X265": "19",
    "MOVIE_XVID": "20",
    "MOVIE_WEB": "58",
    "TV_480P": "21",
    "TV_4K": "22",
    "TV_BLURAY": "23",
    "TV_DVDRIP": "25",
    "TV_X264": "30",
    "TV_X265": "31",
    "TV_XVID": "32",
    "TV_WEB": "59",
    "ANIME": "43",
}

_SD_RESOLUTIONS = {"480p", "480i", "576p", "576i"}
_UHD_RESOLUTIONS = {"2160p", "4320p", "8640p"}
# The upload guide bans < > : " / \ | ? *, but the naming guide spells DTS:X, so only a title colon ("Mission: Impossible") goes.
_FORBIDDEN_TITLE_CHARS = re.compile(r'[<>"/\\|?*]|:(?=\s)')


class ZeroDayFiles(UNIT3D):
    """
    0DayFiles (0DF) — UNIT3D private tracker with scene-style categories.
    """

    tracker = "0DAYFILES"
    display_name = "0DayFiles"
    base_url = "https://0dayfiles.net"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("MOVIE", "TV")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="0DAYFILES")
        self.config = config
        self.common = Common(config)

    @staticmethod
    def _category_key(meta: Meta) -> str:
        """First match wins: disc, 4K, SD, WEB, x265 encode, Blu-ray, XviD, x264."""
        if meta.anime:
            return "ANIME"
        prefix = "TV" if meta.category == "TV" else "MOVIE"
        release_type = meta.type or ""
        encode = f"{meta.video_encode} {meta.video_codec}".upper()

        if meta.is_disc:
            if meta.is_disc == "DVD":
                return "TV_DVDRIP" if prefix == "TV" else "MOVIE_DVDR"
            return "TV_BLURAY" if prefix == "TV" else "MOVIE_BLURAY_FULL"
        if meta.resolution in _UHD_RESOLUTIONS:
            return f"{prefix}_4K"
        if meta.sd or meta.resolution in _SD_RESOLUTIONS:
            if prefix == "TV" and release_type == "DVDRIP":
                return "TV_DVDRIP"
            return f"{prefix}_480P"
        if release_type in ("WEBDL", "WEBRIP"):
            return f"{prefix}_WEB"
        if release_type in ("ENCODE", "HDTV") and ("HEVC" in encode or "265" in encode):
            return f"{prefix}_X265"
        if "XVID" in encode:
            return f"{prefix}_XVID"
        if release_type in ("REMUX", "ENCODE"):
            return f"{prefix}_BLURAY"
        return f"{prefix}_X264"

    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        if reverse:
            return {v: k for k, v in CATEGORY_IDS.items()}
        resolved = CATEGORY_IDS.get(self._category_key(meta), "0") if (category or meta.category) in ("MOVIE", "TV") else "0"
        if mapping_only:
            mapping = dict(CATEGORY_IDS)
            if meta.category in ("MOVIE", "TV"):
                mapping[meta.category] = resolved
            return mapping
        return {"category_id": resolved}

    async def get_name(self, meta: Meta) -> dict[str, str]:
        name = (await super().get_name(meta))["name"]
        return {"name": " ".join(_FORBIDDEN_TITLE_CHARS.sub("", name).split())}

    async def get_data(self, meta: Meta) -> dict[str, str]:
        data = await super().get_data(meta)
        data.pop("type_id", None)
        data.pop("resolution_id", None)
        return data

    async def get_additional_data(self, meta: Meta) -> dict[str, str]:
        # Only honoured for trusted uploaders; everyone else is queued anyway.
        return {"mod_queue_opt_in": await self.get_flag(meta, "modq")}

    async def process_response_data(self, response_data: dict[str, Any]) -> str:
        message = await super().process_response_data(response_data)
        # A possible dupe still answers success: true, but waits for staff before it goes live.
        if response_data.get("status") == "held_for_moderation":
            return f"{message} (held for staff review as a possible dupe; seed it now, it goes live once approved)"
        return message

    async def get_search_urls(self, meta: Meta, request_params: ParamsList) -> list[tuple[str, ParamsList, bool]]:
        # Torrents here carry no type or resolution, so filtering on them would hide every dupe.
        params = [(k, v) for k, v in request_params if k not in ("types[]", "resolutions[]")]
        return await super().get_search_urls(meta, params)
