# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any

from src.console import logger
from src.languages import languages_manager
from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]

_GREEK_CODES = {"el", "ell", "gre", "greek"}
_ALLOWED_RESOLUTIONS = {"720p", "1080i", "1080p", "1440p", "2160p", "4320p", "8640p"}


class HellenicHD(UNIT3D):
    """
    Hellenic-HD (HEL) — Greek UNIT3D private tracker.
    """

    tracker = "HELLENICHD"
    display_name = "Hellenic-HD"
    base_url = "https://hellenic-hd.cc"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    requests_url = f"{base_url}/api/requests/filter"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("MOVIE", "TV")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="HELLENICHD")
        self.config = config
        self.common = Common(config)

    # Types (1-6) and resolutions (1-9, Other=10) match the UNIT3D defaults.
    # Movies and series are split by whether Greek subtitles are present.
    async def get_category_id(self, meta: Meta, category: str = "", reverse: bool = False, mapping_only: bool = False) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "SPORTS": "14",
            "MOVIE_NO_GREEK_SUBS": "20",
            "TV_NO_GREEK_SUBS": "21",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category or meta.category or ""
        if meta.is_sports:
            resolved_category = "SPORTS"
        elif resolved_category in {"MOVIE", "TV"} and not await self._has_greek_subtitles(meta):
            resolved_category = f"{resolved_category}_NO_GREEK_SUBS"
        return {"category_id": category_id.get(resolved_category, "0")}

    async def get_additional_checks(self, meta: Meta) -> bool:
        # Site rules: 720p and above only, and every upload must carry subtitles
        # (muxed or a sidecar file) in any language.
        if meta.resolution not in _ALLOWED_RESOLUTIONS:
            logger.info(f"{self.tracker}: [bold red]only accepts 720p and above (this release is {meta.resolution or 'an unknown resolution'}).[/bold red]")
            return False
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        if not meta.subtitle_languages and not meta.subtitle_files:
            logger.info(f"{self.tracker}: [bold red]requires subtitles, either inside the container or as a separate subtitle file.[/bold red]")
            return False
        return True

    @staticmethod
    def _is_greek(value: Any) -> bool:
        language = re.sub(r"\s*\([^)]*\)", "", str(value or "")).strip().casefold()
        return language in _GREEK_CODES or language.startswith("greek")

    async def _has_greek_subtitles(self, meta: Meta) -> bool:
        """Greek subtitles either muxed into the video or as a sidecar file (e.g. Movie.el.srt)."""
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        languages = meta.subtitle_languages
        if any(self._is_greek(language) for language in ([languages] if isinstance(languages, str) else languages or [])):
            return True
        for subtitle_file in meta.subtitle_files or []:
            tokens = re.split(r"[.\s_\-\[\]()]+", Path(str(subtitle_file)).stem)
            if any(token.casefold() in _GREEK_CODES for token in tokens):
                return True
        return False
