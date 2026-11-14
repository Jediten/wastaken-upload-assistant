# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Find a book's identifier from its title and author when the files carry none.

The book providers (Audible, Google Books, OpenLibrary, MyAnonamouse) all
need an ASIN, ISBN or work ID before they return anything. Files ripped
outside Audible rarely embed one, so this module searches Audible's public
catalog and OpenLibrary by title and author, ranks the candidates against
what the files say (title, author, narrator, running time) and either picks
the obvious match or asks.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import cli_ui
import httpx

from src import webui_events
from src.audible import _ASIN_RE, _parse_product, normalize_audible_domain
from src.console import logger, prompt_in_thread
from src.meta import Meta
from src.metadata_cache import cache_for, is_cache_miss

DEFAULT_AUDIBLE_DOMAIN = "audible.com"
_AUDIO_FORMAT_RE = re.compile(r"audio|\bcd\b|mp3|cassette|playaway", re.IGNORECASE)
_SERIES_PREFIX_RE = re.compile(r"^[A-Z]{1,4}\d{1,2}\s*[-:]\s*", re.IGNORECASE)
_TRAILING_SERIES_RE = re.compile(r"\s*[\(\[][^\)\]]*(?:book|vol(?:ume)?|#)\s*\d+[^\)\]]*[\)\]]\s*$", re.IGNORECASE)
_SUBTITLE_SPLIT_RE = re.compile(r"\s*[:\u2013\u2014]\s+|\s+-\s+")

# A running time this close to the catalog's is the same recording.
RUNTIME_TOLERANCE = 0.03
# Pick without asking above this score (see ``rank_candidates``).
AUTO_PICK_SCORE = 0.85


def normalize_text(value: Any) -> str:
    """Lower-case, strip punctuation and collapse spaces for comparisons."""
    text = str(value or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_search_title(title: str) -> str:
    """Drop series prefixes like ``HG1 -`` and trailing ``(Book 2)`` from a tag title."""
    value = str(title or "").strip()
    value = _SERIES_PREFIX_RE.sub("", value)
    value = _TRAILING_SERIES_RE.sub("", value)
    return value.strip(" -:") or str(title or "").strip()


def title_query_variants(title: str) -> list[str]:
    """The cleaned title first, then the same without its subtitle, each once."""
    cleaned = clean_search_title(title)
    if not cleaned:
        return []
    variants = [cleaned]
    head = _SUBTITLE_SPLIT_RE.split(cleaned, maxsplit=1)[0].strip(" -:")
    if head and normalize_text(head) != normalize_text(cleaned):
        variants.append(head)
    return variants


def split_release_name(name: str) -> tuple[str, str]:
    """Return (author, title) from a folder named ``Author - Title`` or ``Author - Series - Title``."""
    parts = [part.strip() for part in re.split(r"\s+[-–]\s+", str(name or "")) if part.strip()]  # noqa: RUF001
    if len(parts) < 2:
        return "", clean_search_title(parts[0]) if parts else ""
    return parts[0], clean_search_title(parts[-1])


def similarity(left: Any, right: Any) -> float:
    a, b = normalize_text(left), normalize_text(right)
    if not a or not b:
        return 0.0
    if a == b or a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _names_match(wanted: str, found: str) -> float:
    """Best similarity between any listed person on each side."""
    if not wanted or not found:
        return 0.0
    wanted_names = [n for n in re.split(r",|&| and ", wanted) if n.strip()]
    found_names = [n for n in re.split(r",|&| and ", found) if n.strip()]
    return max((similarity(w, f) for w in wanted_names for f in found_names), default=0.0)


def _runtime_match(candidate_minutes: Any, duration_seconds: float | None) -> float | None:
    """Return the relative runtime difference, or None when either side is unknown."""
    if not duration_seconds or not isinstance(candidate_minutes, int) or candidate_minutes <= 0:
        return None
    return abs(candidate_minutes * 60 - duration_seconds) / duration_seconds


async def search_audible_catalog(title: str, author: str, domain: str, base_dir: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Search Audible's public catalog by title (and author) and return parsed products with their ASIN."""
    title = str(title or "").strip()
    if not title:
        return []
    try:
        domain = normalize_audible_domain(domain or DEFAULT_AUDIBLE_DOMAIN)
    except ValueError:
        return []
    cache = cache_for(base_dir)
    cache_key = f"v1:{domain}:{normalize_text(title)}:{normalize_text(author)}:{limit}"
    cached = await cache.get("audible", "search", cache_key)
    if not is_cache_miss(cached) and isinstance(cached, list):
        return cached
    params: dict[str, Any] = {
        "title": title,
        "num_results": limit,
        "products_sort_by": "Relevance",
        "response_groups": "contributors,media,product_attrs,product_desc,product_details,product_extended_attrs,rating,series",
        "image_sizes": "1215,900,500",
    }
    if author:
        params["author"] = author
    results: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(f"https://api.{domain}/1.0/catalog/products", params=params)
            if response.status_code != 200:
                logger.debug(f"[yellow]Audible catalog search returned {response.status_code} for {title!r}[/yellow]")
                return []
            payload = response.json()
            for product in payload.get("products", []) if isinstance(payload, dict) else []:
                asin = str(product.get("asin", "")).strip().upper() if isinstance(product, dict) else ""
                if not _ASIN_RE.fullmatch(asin):
                    continue
                parsed = _parse_product(product, asin)
                if parsed:
                    parsed["asin"] = asin
                    parsed["source"] = "audible"
                    parsed["domain"] = domain
                    results.append(parsed)
    except (httpx.HTTPError, ValueError) as error:
        logger.debug(f"[yellow]Audible catalog search failed for {title!r}: {error}[/yellow]")
        return []
    await cache.set("audible", "search", cache_key, results, negative=not results)
    return results


def _edition_isbn(edition: dict[str, Any]) -> str:
    for key in ("isbn_13", "isbn_10"):
        values = edition.get(key)
        if isinstance(values, list):
            for value in values:
                digits = re.sub(r"[^0-9Xx]", "", str(value))
                if digits:
                    return digits
    return ""


def _edition_narrator(edition: dict[str, Any]) -> str:
    names: list[str] = []
    for key in ("contributors", "contributions"):
        for item in edition.get(key) or []:
            if isinstance(item, dict) and "narrat" in str(item.get("role", "")).lower() and item.get("name"):
                names.append(str(item["name"]).strip())
            elif isinstance(item, str) and "narrat" in item.lower():
                names.append(re.sub(r"(?i)narrat(?:or|ed by)?\s*[:\-]?\s*", "", item).strip())
    return ", ".join(dict.fromkeys(n for n in names if n))


def _edition_year(edition: dict[str, Any]) -> int | None:
    match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(edition.get("publish_date") or ""))
    return int(match.group(1)) if match else None


def _edition_language(edition: dict[str, Any]) -> str:
    for item in edition.get("languages") or []:
        key = item.get("key", "") if isinstance(item, dict) else str(item)
        code = key.rsplit("/", 1)[-1].strip()
        if code:
            return code
    return ""


async def search_openlibrary_editions(title: str, author: str, base_dir: str, *, audiobook: bool, works_limit: int = 3) -> list[dict[str, Any]]:
    """Search OpenLibrary works by title/author, then collect editions with an ISBN.

    For audiobooks only audio editions (CD, MP3, audio download) are kept so the
    ISBN names the recording, which is what trackers ask for.
    """
    title = str(title or "").strip()
    if not title:
        return []
    cache = cache_for(base_dir)
    cache_key = f"v1:{normalize_text(title)}:{normalize_text(author)}:{int(audiobook)}:{works_limit}"
    cached = await cache.get("openlibrary", "search", cache_key)
    if not is_cache_miss(cached) and isinstance(cached, list):
        return cached
    params: dict[str, Any] = {"title": title, "fields": "key,title,author_name,first_publish_year,cover_i", "limit": 10}
    if author:
        params["author"] = author
    results: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get("https://openlibrary.org/search.json", params=params)
            if response.status_code != 200:
                logger.debug(f"[yellow]OpenLibrary search returned {response.status_code} for {title!r}[/yellow]")
                return []
            payload = response.json()
            docs = [doc for doc in payload.get("docs", []) if isinstance(doc, dict) and str(doc.get("key", "")).startswith("/works/")]
            # Collections and box sets rank below the single work.
            docs.sort(key=lambda doc: (similarity(title, doc.get("title")) < 0.6, " / " in str(doc.get("title", ""))))
            for doc in docs[:works_limit]:
                work_id = str(doc["key"]).rsplit("/", 1)[-1]
                work_title = str(doc.get("title") or "").strip()
                work_author = ", ".join(str(name) for name in doc.get("author_name") or [] if name)
                cover_id = doc.get("cover_i")
                editions_response = await client.get(f"https://openlibrary.org/works/{work_id}/editions.json", params={"limit": 200})
                if editions_response.status_code != 200:
                    continue
                entries = editions_response.json().get("entries", [])
                for edition in entries if isinstance(entries, list) else []:
                    if not isinstance(edition, dict):
                        continue
                    physical_format = str(edition.get("physical_format") or "")
                    is_audio = bool(_AUDIO_FORMAT_RE.search(physical_format))
                    if audiobook != is_audio:
                        continue
                    isbn = _edition_isbn(edition)
                    if not isbn:
                        continue
                    results.append(
                        {
                            "source": "openlibrary",
                            "work_id": work_id,
                            "edition_id": str(edition.get("key", "")).rsplit("/", 1)[-1],
                            "isbn": isbn,
                            "title": str(edition.get("title") or work_title).strip(),
                            "author": work_author,
                            "narrator": _edition_narrator(edition),
                            "publisher": ", ".join(str(p) for p in edition.get("publishers") or [] if p),
                            "year": _edition_year(edition),
                            "physical_format": physical_format,
                            "language": _edition_language(edition),
                            "artwork_url": f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if isinstance(cover_id, int) and cover_id > 0 else "",
                        }
                    )
    except (httpx.HTTPError, ValueError) as error:
        logger.debug(f"[yellow]OpenLibrary search failed for {title!r}: {error}[/yellow]")
        return []
    await cache.set("openlibrary", "search", cache_key, results, negative=not results)
    return results


def rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    title: str,
    author: str = "",
    narrator: str = "",
    duration_seconds: float | None = None,
) -> list[tuple[dict[str, Any], float]]:
    """Score each candidate from 0 to 1 against what the files say and sort best first.

    Title carries most of the weight. A running time within ``RUNTIME_TOLERANCE``
    of the files identifies the recording, so it adds to the score; one far off
    takes away from it. Author and narrator refine the order between editions.
    """
    ranked: list[tuple[dict[str, Any], float]] = []
    for candidate in candidates:
        score = 0.6 * similarity(title, candidate.get("title"))
        score += 0.2 * (_names_match(author, str(candidate.get("author") or "")) if author else 0.5)
        score += 0.1 * (_names_match(narrator, str(candidate.get("narrator") or "")) if narrator and candidate.get("narrator") else 0.5)
        drift = _runtime_match(candidate.get("runtime_minutes"), duration_seconds)
        if drift is None:
            score += 0.05
        elif drift <= RUNTIME_TOLERANCE:
            score += 0.1
        elif drift > 0.25:
            score -= 0.25
        candidate["runtime_drift"] = drift
        ranked.append((candidate, max(0.0, min(1.0, score))))
    ranked.sort(key=lambda item: item[1], reverse=True)
    # The same ISBN or ASIN appears once, best score first.
    seen: set[str] = set()
    unique: list[tuple[dict[str, Any], float]] = []
    for candidate, score in ranked:
        key = str(candidate.get("asin") or candidate.get("isbn") or id(candidate))
        if key in seen:
            continue
        seen.add(key)
        unique.append((candidate, score))
    return unique


def _minutes_label(minutes: Any) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m" if isinstance(minutes, int) and minutes > 0 else ""


def _candidate_label(candidate: dict[str, Any]) -> str:
    """One line naming the entry: title, year and who reads it."""
    bits = [str(candidate.get("title") or "?")]
    if candidate.get("year"):
        bits.append(f"({candidate['year']})")
    if candidate.get("narrator"):
        bits.append(f"read by {candidate['narrator']}")
    return " ".join(bits)


def _candidate_meta(candidate: dict[str, Any], score: float | None = None) -> str:
    """The facts that tell editions apart, as one ``a · b · c`` line."""
    identifier = f"Audible ASIN {candidate.get('asin', '')}" if candidate.get("source") == "audible" else f"ISBN {candidate.get('isbn', '')}"
    drift = candidate.get("runtime_drift")
    runtime = _minutes_label(candidate.get("runtime_minutes"))
    if runtime and isinstance(drift, float):
        runtime += " (matches the files)" if drift <= RUNTIME_TOLERANCE else f" ({drift:.0%} off the files)"
    parts = (
        identifier,
        f"Author: {candidate['author']}" if candidate.get("author") else "",
        f"Publisher: {candidate['publisher']}" if candidate.get("publisher") else "",
        f"Runtime: {runtime}" if runtime else "",
        f"Format: {candidate['physical_format']}" if candidate.get("physical_format") else "",
        f"Language: {candidate['language']}" if candidate.get("language") else "",
        f"Score: {score:.2f}" if score is not None else "",
    )
    return " · ".join(part for part in parts if part)


def _candidate_link(candidate: dict[str, Any]) -> tuple[str, str]:
    if candidate.get("source") == "audible":
        return f"https://www.{candidate.get('domain', DEFAULT_AUDIBLE_DOMAIN)}/pd/{candidate.get('asin', '')}", "Audible"
    return f"https://openlibrary.org/books/{candidate.get('edition_id', '')}", "OpenLibrary"


def _file_facts(meta: Meta, duration_seconds: float | None) -> str:
    """What the files say, so the entries can be judged against it."""
    parts = (
        f"Title: {meta.title}" if meta.title else "",
        f"Author: {meta.author}" if meta.author else "",
        f"Narrator: {meta.narrator}" if meta.narrator else "",
        f"Runtime: {_minutes_label(int(duration_seconds // 60))}" if duration_seconds else "",
        f"Year: {meta.year}" if meta.year else "",
    )
    return " · ".join(part for part in parts if part)


async def choose_book_candidate(meta: Meta, ranked: list[tuple[dict[str, Any], float]], *, duration_seconds: float | None = None) -> dict[str, Any] | None:
    """Pick the match: automatically when it is clear, otherwise by asking.

    A pick is clear when the best entry scores highly and either leads the
    runner-up comfortably, or its running time or narrator confirms it is
    the same recording. Unattended runs only accept such a pick. Otherwise
    every entry is shown with the facts needed to tell them apart, next to
    what the files themselves say. Pressing Enter keeps the upload going
    with the embedded metadata only.
    """
    if not ranked:
        return None
    best, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    runtime_confirms = best.get("runtime_drift") is not None and best["runtime_drift"] <= RUNTIME_TOLERANCE
    narrator_confirms = bool(meta.narrator) and _names_match(meta.narrator, str(best.get("narrator") or "")) >= 0.8
    clear_winner = best_score >= AUTO_PICK_SCORE and (best_score - second_score >= 0.1 or runtime_confirms or narrator_confirms)
    if clear_winner:
        logger.info(f"[green]Book match: {_candidate_label(best)} [{_candidate_meta(best, best_score)}][/green]")
        return best
    if meta.unattended:
        logger.info(f"[yellow]No clear book match for {meta.title!r}; continuing with embedded metadata.[/yellow]")
        return None

    facts = _file_facts(meta, duration_seconds)
    logger.info("")
    logger.info("[bold yellow]The files carry no ISBN or ASIN, and the catalogs have more than one plausible entry.[/bold yellow]")
    if facts:
        logger.info(f"[yellow]The files say:[/yellow] {facts}")
    logger.info("")
    labels: list[str] = []
    images: list[str] = []
    details: list[dict[str, str]] = []
    for index, (candidate, score) in enumerate(ranked, start=1):
        label = _candidate_label(candidate)
        link, link_label = _candidate_link(candidate)
        meta_line = _candidate_meta(candidate, score)
        overview = str(candidate.get("overview") or "").strip()
        logger.info(f"[cyan]{index}.[/cyan] [bold]{label}[/bold]")
        logger.info(f"   [dim]{meta_line}[/dim]")
        if overview:
            logger.info(f"   [green]Overview:[/green] {overview[:200]}{'...' if len(overview) > 200 else ''}")
        logger.info(f"   [dim]{link}[/dim]")
        logger.info("")
        labels.append(label)
        images.append(str(candidate.get("artwork_url") or ""))
        details.append({"meta": meta_line, "text": overview[:400], "link": link, "link_label": link_label})
    hint = "The files carry no ISBN or ASIN, so the catalogs were searched by title and author."
    if facts:
        hint += f"\nThe files say: {facts}"
    while True:
        with webui_events.numbered_options(labels, actions=[("", "None of these")], images=images, details=details, hint=hint):
            answer = await prompt_in_thread(cli_ui.ask_string, "Enter the number of the correct entry, or press Enter to continue without one: ") or ""
        answer = answer.strip()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(ranked):
            return ranked[int(answer) - 1][0]
        logger.info(f"[red]Enter a number from 1 to {len(ranked)}, or press Enter.[/red]")


async def find_book_identifier(meta: Meta, base_dir: str, config: dict[str, Any] | None, *, duration_seconds: float | None = None) -> dict[str, Any] | None:
    """Search the catalogs for the book described by the files and return the chosen candidate.

    The tag title is tried first; when it finds nothing, the title without
    its subtitle is tried, since subtitles like "A Hunger Games Novel" are
    not part of catalog titles.
    """
    release_author, release_title = split_release_name(meta.basename_no_ext or "")
    variants = title_query_variants(meta.title) or title_query_variants(release_title)
    if not variants:
        return None
    author = str(meta.author or "").strip() or release_author
    narrator = str(meta.narrator or "").strip()
    domain = str((config or {}).get("DEFAULT", {}).get("audible_domain", "") or "").strip() or DEFAULT_AUDIBLE_DOMAIN
    candidates: list[dict[str, Any]] = []
    title = variants[0]
    for title in variants:
        logger.info(f"[cyan]Searching catalogs for {title!r}{' by ' + author if author else ''}...[/cyan]")
        if meta.audiobook:
            candidates.extend(await search_audible_catalog(title, author, domain, base_dir))
        candidates.extend(await search_openlibrary_editions(title, author, base_dir, audiobook=bool(meta.audiobook)))
        if candidates:
            break
    if not candidates:
        logger.info(f"[yellow]No catalog match for {title!r}; continuing with embedded metadata.[/yellow]")
        return None
    ranked = rank_candidates(candidates, title=title, author=author, narrator=narrator, duration_seconds=duration_seconds)[:8]
    return await choose_book_candidate(meta, ranked, duration_seconds=duration_seconds)
