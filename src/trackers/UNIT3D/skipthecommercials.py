# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any

from src.console import logger
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.rehostimages import ImageHostPolicy, RehostImagesManager
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class SkipTheCommercials(UNIT3D):
    """
    SkipTheCommercials (STC) is a Private Torrent Tracker for TV and
    documentary movies.
    """

    tracker = "SKIPTHECOMMERCIALS"
    display_name = "SkipTheCommercials"
    allows_bloated_audio = True
    base_url = "https://skipthecommercials.xyz"
    banned_groups = (
        "-ZR-",
        "126811",
        "4K4U",
        "Aisha",
        "Aisha@RFX",
        "Alcaide_Kira",
        "AOS",
        "ARCADE",
        "AV1D",
        "aXXo",
        "B3LLUM",
        "BiTOR",
        "BONE",
        "BRrip",
        "CM8",
        "CREATiVE24",
        "CrEwSaDe",
        "CTFOH",
        "d3g",
        "dAV1nci",
        "DepraveD",
        "DNL",
        "EGEN",
        "eranger2",
        "EVO",
        "FaNGDiNG0",
        "FGT",
        "flower",
        "FoxTorrentX",
        "GalaxyTV",
        "HD2DVD",
        "HDHub4u",
        "HDT",
        "HDTime",
        "iHYTECH",
        "ION10",
        "iPlanet",
        "iVy",
        "KaPPa",
        "KiNGDOM",
        "LAMA",
        "MeGusta",
        "mHD",
        "mSD",
        "NaNi",
        "NhaNc3",
        "nHD",
        "nikt0",
        "nSD",
        "OFT",
        "OldT",
        "PAAI",
        "PANDEMONiUM",
        "PHOCiS",
        "PiGNUS",
        "PRODJi",
        "PSA",
        "R&H",
        "RARBG",
        "Rifftrax",
        "SANTi",
        "SasukeducK",
        "seedpool",
        "SEEDSTER",
        "ShAaNiG",
        "Sicario",
        "SP3LL",
        "SPx",
        "STUTTERSHIT",
        "TAoE",
        "TEKNO3D",
        "TGALAXY",
        "TGx",
        "tokar86a",
        "TORRENTGALAXY",
        "ToVaR",
        "TSP",
        "TSPxL",
        "UnKn0wn",
        "ViSION",
        "VN_Foxcore",
        "VXT",
        "WAF",
        "WKS",
        "x0r",
        "YIFY",
        "YTS",
        "YTS.MX",
        "ZR",
    )
    approved_image_hosts = ("imgbox", "imgbb", "onlyimage", "ptscreens")
    image_host_policy = ImageHostPolicy({"ibb.co": "imgbb", "imgbox.com": "imgbox", "onlyimage.org": "onlyimage", "ptscreens.com": "ptscreens"}, approved_image_hosts)
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    tracker_urls = ("https://skipthecommercials.xyz",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="SKIPTHECOMMERCIALS")
        self.config: Config = config
        self.common = Common(config)
        self.rehost_images_manager = RehostImagesManager(config)

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_value = str(meta.type)
        type_id = {"DISC": "1", "REMUX": "2", "WEBDL": "4", "WEBRIP": "5", "HDTV": "6", "ENCODE": "3"}.get(type_value, "0")
        if meta.tv_pack:
            is_web = type_value in ["WEBDL", "WEBRIP"]
            type_id = ("17" if not is_web else "14") if meta.sd else ("18" if not is_web else "13")

        return {"type_id": type_id}

    async def get_additional_checks(self, meta: Meta) -> bool:
        category = str(meta.category).upper()
        combined_genres = meta.combined_genres if isinstance(meta.combined_genres, list) else [genre.strip() for genre in str(meta.combined_genres).split(",") if genre.strip()]
        documentary_metadata = [*(meta.genres or []), *(meta.keywords or []), *combined_genres]
        is_documentary = any(str(value).strip().lower() in {"documentary", "documentaries"} for value in documentary_metadata)

        if category != "TV" and not (category == "MOVIE" and is_documentary):
            if not meta.unattended:
                logger.info(f"{self.tracker}: [bold red]Only TV and documentary movie uploads are allowed at {self.tracker}.[/bold red]")
            return False

        passed = True
        genres = ", ".join(str(value) for value in [*(meta.keywords or []), *combined_genres])
        adult_keywords = ["xxx", "erotic", "porn", "adult", "orgy", "hentai", "adult animation", "softcore"]
        if any(re.search(rf"(^|,\s*){re.escape(keyword)}(\s*,|$)", genres, re.IGNORECASE) for keyword in adult_keywords):
            logger.info(f"{self.tracker}: [bold red]Porn is not allowed at {self.tracker}.[/bold red]")
            passed = False

        if not meta.valid_mi_settings:
            logger.info(f"{self.tracker}: [bold red]No encoding settings in mediainfo, skipping {self.tracker} upload.[/bold red]")
            return False

        language_ok = meta.is_disc in ["BDMV", "DVD"] or await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["english"], check_audio=True, check_subtitle=True, original_language=True
        )
        return language_ok and passed

    async def get_name(self, meta: Meta) -> dict[str, str]:
        stc_name = meta.name

        # Non-English audio gets its language ahead of the audio codec; full discs are exempt
        if meta.is_disc not in ["BDMV", "DVD"]:
            if not meta.language_checked:
                await languages_manager.process_desc_language(meta, tracker=self.tracker)
            audio_languages: list[str] = [] if not meta.audio_languages else meta.audio_languages
            audio = meta.audio or ""
            if audio_languages and not await languages_manager.has_english_language(audio_languages):
                foreign_lang = audio_languages[0].upper()
                if audio and foreign_lang not in stc_name.upper():
                    stc_name = stc_name.replace(audio, f"{foreign_lang} {audio}", 1)

        if not str(meta.tag or "").strip("- "):
            stc_name = f"{stc_name}-NOGROUP"

        return {"name": stc_name}

    async def get_description(self, meta: Meta) -> dict[str, str]:
        return {
            "description": await DescriptionBuilder(self.tracker, self.config).general_description_generator(
                meta,
                mediainfo=False,
                nfo=False,
                approved_image_hosts=self.approved_image_hosts,
            )
        }
