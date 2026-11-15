# ruff: noqa: S101
"""Books without an ISBN or ASIN are found in the catalogs by title and author."""

from unittest.mock import AsyncMock

import httpx
import pytest

from src import book_prep, book_search
from src.book_search import (
    choose_book_candidate,
    clean_search_title,
    find_book_identifier,
    rank_candidates,
    search_audible_catalog,
    search_openlibrary_editions,
    split_release_name,
    title_query_variants,
)
from src.meta import Meta

ASIN = "B0SRCH1234"


def _audible_product(**overrides):
    product = {
        "asin": ASIN,
        "title": "The Invented Debt",
        "authors": [{"name": "Mira Example"}],
        "narrators": [{"name": "Tara Sample"}],
        "publisher_name": "Fictional Audio",
        "publisher_summary": "An invented synopsis.",
        "release_date": "2008-10-01",
        "language": "english",
        "runtime_length_min": 671,
        "product_images": {"500": "https://example.org/cover.jpg"},
    }
    product.update(overrides)
    return product


def _mock_http(monkeypatch, respond):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(book_search.httpx, "AsyncClient", lambda **_kwargs: real_client(transport=httpx.MockTransport(respond)))


def test_clean_search_title_strips_series_prefix_and_trailing_book_number():
    assert clean_search_title("HG1 - The Hunger Games") == "The Hunger Games"
    assert clean_search_title("Mockingjay (Hunger Games, Book 3)") == "Mockingjay"
    assert clean_search_title("Plain Title") == "Plain Title"


def test_title_query_variants_retry_without_the_subtitle():
    assert title_query_variants("Mockingjay: The Final Book of The Hunger Games") == ["Mockingjay: The Final Book of The Hunger Games", "Mockingjay"]
    assert title_query_variants("The Ballad of Songbirds and Snakes: A Hunger Games Novel") == [
        "The Ballad of Songbirds and Snakes: A Hunger Games Novel",
        "The Ballad of Songbirds and Snakes",
    ]
    assert title_query_variants("The 100") == ["The 100"]
    assert title_query_variants("") == []
    # A trailing bracket that is not a book number is tried without, after the full title
    assert title_query_variants("Homecoming (The Hundred 3)") == ["Homecoming (The Hundred 3)", "Homecoming"]
    assert title_query_variants("Hamlet [Arkangel Shakespeare] (Unabridged)") == ["Hamlet [Arkangel Shakespeare] (Unabridged)", "Hamlet"]
    assert title_query_variants("(500) Days") == ["(500) Days"]


def test_split_release_name_takes_author_and_last_segment():
    assert split_release_name("Suzanne Collins - The Hunger Games, Book 01 - The Hunger Games") == ("Suzanne Collins", "The Hunger Games")
    assert split_release_name("Only A Title") == ("", "Only A Title")


@pytest.mark.asyncio
async def test_audible_search_parses_products_and_caches(tmp_path, monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"products": [_audible_product(), {"asin": "bad", "title": "ignored"}]})

    _mock_http(monkeypatch, respond)
    first = await search_audible_catalog("The Invented Debt", "Mira Example", "audible.com", str(tmp_path))
    second = await search_audible_catalog("The Invented Debt", "Mira Example", "audible.com", str(tmp_path))

    assert len(calls) == 1
    assert calls[0].url.host == "api.audible.com"
    assert calls[0].url.params["title"] == "The Invented Debt"
    assert calls[0].url.params["author"] == "Mira Example"
    assert first == second
    assert len(first) == 1
    assert first[0]["asin"] == ASIN
    assert first[0]["source"] == "audible"
    assert first[0]["narrator"] == "Tara Sample"
    assert first[0]["runtime_minutes"] == 671


@pytest.mark.asyncio
async def test_openlibrary_search_keeps_only_audio_editions_for_audiobooks(tmp_path, monkeypatch):
    def respond(request):
        if request.url.path == "/search.json":
            return httpx.Response(
                200,
                json={
                    "docs": [
                        {"key": "/works/OL1W", "title": "The Invented Debt", "author_name": ["Mira Example"], "first_publish_year": 2008, "cover_i": 77},
                        {"key": "/works/OL2W", "title": "The Invented Debt / Sequel", "author_name": ["Mira Example"]},
                    ]
                },
            )
        if request.url.path == "/works/OL1W/editions.json":
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {"key": "/books/OL1M", "title": "The Invented Debt", "physical_format": "Hardcover", "isbn_13": ["9780000000019"], "publishers": ["Paper House"]},
                        {
                            "key": "/books/OL2M",
                            "title": "The Invented Debt",
                            "physical_format": "Audio CD",
                            "isbn_13": ["9780000000026"],
                            "publishers": ["Fictional Audio"],
                            "publish_date": "October 2008",
                            "contributors": [{"role": "Narrator", "name": "Tara Sample"}],
                            "languages": [{"key": "/languages/eng"}],
                        },
                    ]
                },
            )
        if request.url.path == "/works/OL2W/editions.json":
            return httpx.Response(200, json={"entries": []})
        return httpx.Response(404)

    _mock_http(monkeypatch, respond)
    audio = await search_openlibrary_editions("The Invented Debt", "Mira Example", str(tmp_path), audiobook=True)
    print_editions = await search_openlibrary_editions("The Invented Debt", "Mira Example", str(tmp_path), audiobook=False)

    assert [c["isbn"] for c in audio] == ["9780000000026"]
    assert audio[0] == {
        "source": "openlibrary",
        "work_id": "OL1W",
        "edition_id": "OL2M",
        "isbn": "9780000000026",
        "title": "The Invented Debt",
        "author": "Mira Example",
        "narrator": "Tara Sample",
        "publisher": "Fictional Audio",
        "year": 2008,
        "physical_format": "Audio CD",
        "language": "eng",
        "artwork_url": "https://covers.openlibrary.org/b/id/77-L.jpg",
    }
    assert [c["isbn"] for c in print_editions] == ["9780000000019"]


def test_rank_prefers_runtime_match_and_dedupes():
    short = {"source": "audible", "asin": "B0SHORT123", "title": "The Invented Debt", "author": "Mira Example", "narrator": "Other Reader", "runtime_minutes": 400}
    exact = {"source": "audible", "asin": "B0EXACT123", "title": "The Invented Debt", "author": "Mira Example", "narrator": "Tara Sample", "runtime_minutes": 671}
    duplicate = dict(exact)
    other = {"source": "openlibrary", "isbn": "9780000000026", "title": "A Different Book", "author": "Someone Else"}

    ranked = rank_candidates([short, other, exact, duplicate], title="The Invented Debt", author="Mira Example", narrator="Tara Sample", duration_seconds=671 * 60 + 12)

    assert [c["asin"] if "asin" in c else c["isbn"] for c, _ in ranked] == ["B0EXACT123", "B0SHORT123", "9780000000026"]
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]
    assert ranked[0][0]["runtime_drift"] < book_search.RUNTIME_TOLERANCE


@pytest.mark.asyncio
async def test_choose_auto_picks_clear_winner_and_skips_in_unattended(monkeypatch):
    asked = AsyncMock(return_value="")
    monkeypatch.setattr(book_search, "prompt_in_thread", asked)
    winner = {"source": "audible", "asin": ASIN, "title": "The Invented Debt", "runtime_drift": 0.001}
    runner_up = {"source": "openlibrary", "isbn": "9780000000026", "title": "The Invented Debt", "runtime_drift": None}

    assert await choose_book_candidate(Meta(unattended=True), [(winner, 0.95), (runner_up, 0.9)]) is winner
    assert asked.await_count == 0
    assert await choose_book_candidate(Meta(unattended=True, title="x"), [(winner, 0.7), (runner_up, 0.65)]) is None
    assert asked.await_count == 0


@pytest.mark.asyncio
async def test_choose_auto_picks_when_the_narrator_confirms_a_close_race(monkeypatch):
    asked = AsyncMock(return_value="")
    monkeypatch.setattr(book_search, "prompt_in_thread", asked)
    cd = {"source": "openlibrary", "isbn": "9780545091022", "title": "The Hunger Games", "narrator": "Carolyn Mccormick", "runtime_drift": None}
    mp3 = {"source": "openlibrary", "isbn": "9780545114073", "title": "The Hunger Games", "runtime_drift": None}

    assert await choose_book_candidate(Meta(unattended=True, narrator="Carolyn McCorrmick"), [(cd, 0.95), (mp3, 0.9)]) is cd
    assert await choose_book_candidate(Meta(unattended=True, title="x"), [(cd, 0.95), (mp3, 0.9)]) is None
    assert asked.await_count == 0


@pytest.mark.asyncio
async def test_choose_asks_when_unclear_and_accepts_a_number(monkeypatch):
    answers = iter(["9", "2", ""])
    monkeypatch.setattr(book_search, "prompt_in_thread", AsyncMock(side_effect=lambda *_a, **_k: next(answers)))
    first = {"source": "audible", "asin": ASIN, "title": "The Invented Debt", "runtime_drift": None}
    second = {"source": "openlibrary", "isbn": "9780000000026", "title": "The Invented Debt", "runtime_drift": None}

    assert await choose_book_candidate(Meta(), [(first, 0.7), (second, 0.68)]) is second
    assert await choose_book_candidate(Meta(), [(first, 0.7), (second, 0.68)]) is None


@pytest.mark.asyncio
async def test_find_book_identifier_retries_without_the_subtitle(tmp_path, monkeypatch):
    queries = []

    async def fake_audible(title, author, domain, _base_dir, *, limit=10):  # noqa: ARG001
        queries.append(title)
        if title == "Mockingjay":
            return [{"source": "audible", "asin": ASIN, "title": "Mockingjay", "author": author, "runtime_minutes": 700, "domain": domain}]
        return []

    async def fake_openlibrary(title, author, _base_dir, *, audiobook, works_limit=3):  # noqa: ARG001
        queries.append(title)
        return []

    monkeypatch.setattr(book_search, "search_audible_catalog", fake_audible)
    monkeypatch.setattr(book_search, "search_openlibrary_editions", fake_openlibrary)
    meta = Meta(audiobook=True, title="Mockingjay: The Final Book of The Hunger Games", author="Suzanne Collins", unattended=True)

    chosen = await find_book_identifier(meta, str(tmp_path), None, duration_seconds=700 * 60)

    full = "Mockingjay: The Final Book of The Hunger Games"
    assert queries == [full, full, "Mockingjay", "Mockingjay"]
    assert chosen["asin"] == ASIN


@pytest.mark.asyncio
async def test_find_book_identifier_uses_folder_name_when_tags_are_empty(tmp_path, monkeypatch):
    seen = {}

    async def fake_audible(title, author, domain, _base_dir, *, limit=10):  # noqa: ARG001
        seen["audible"] = (title, author, domain)
        return [{"source": "audible", "asin": ASIN, "title": "The Hunger Games", "author": "Suzanne Collins", "runtime_minutes": 671, "domain": domain}]

    async def fake_openlibrary(title, author, _base_dir, *, audiobook, works_limit=3):  # noqa: ARG001
        seen["openlibrary"] = (title, author, audiobook)
        return []

    monkeypatch.setattr(book_search, "search_audible_catalog", fake_audible)
    monkeypatch.setattr(book_search, "search_openlibrary_editions", fake_openlibrary)
    meta = Meta(audiobook=True, basename_no_ext="Suzanne Collins - The Hunger Games, Book 01 - The Hunger Games", unattended=True)

    chosen = await find_book_identifier(meta, str(tmp_path), {"DEFAULT": {"audible_domain": "audible.co.uk"}}, duration_seconds=671 * 60)

    assert seen["audible"] == ("The Hunger Games", "Suzanne Collins", "audible.co.uk")
    assert seen["openlibrary"] == ("The Hunger Games", "Suzanne Collins", True)
    assert chosen["asin"] == ASIN


@pytest.mark.asyncio
async def test_gather_book_prep_fills_metadata_from_the_chosen_audible_match(tmp_path, monkeypatch):
    monkeypatch.setattr(book_prep, "get_audiobook_duration", AsyncMock(return_value=(671 * 60.0, "11h 11m 00s")))
    monkeypatch.setattr(book_prep, "get_audiobook_bitrate", AsyncMock(return_value=192))
    monkeypatch.setattr(
        book_prep,
        "find_book_identifier",
        AsyncMock(return_value={"source": "audible", "asin": ASIN, "title": "The Invented Debt", "domain": "audible.com"}),
    )
    fetched = AsyncMock(
        return_value={
            "title": "The Invented Debt",
            "author": "Mira Example",
            "narrator": "Tara Sample",
            "publisher": "Fictional Audio",
            "overview": "An invented synopsis.",
            "language": "english",
            "year": 2008,
            "runtime_minutes": 671,
            "book_series": "Imaginary Cycle",
            "book_series_index": "1",
            "genres": ["Teen & Young Adult", "Science Fiction & Fantasy", "Dystopian"],
        }
    )
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetched)
    meta = Meta(
        audiobook=True,
        title="HG1 - The Invented Debt",
        author="Mira Example",
        basename_no_ext="Mira Example - The Invented Debt",
        mediainfo={},
        edit=False,
    )
    # The file's own genre tag is the generic "Audiobook"; Audible's genres replace it.
    monkeypatch.setattr(book_prep, "export_info", AsyncMock(return_value={"media": {"track": [{"@type": "General", "Genre": "Audiobook"}]}}))

    await book_prep.gather_book_prep(meta, str(tmp_path / "book.m4b"), str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})

    fetched.assert_awaited_once_with(ASIN, "audible.com", str(tmp_path))
    assert meta.asin == ASIN
    assert meta.audible_url == f"https://www.audible.com/pd/{ASIN}"
    assert (meta.narrator, meta.publisher, meta.overview) == ("Tara Sample", "Fictional Audio", "An invented synopsis.")
    assert (meta.book_language, meta.year) == ("English", 2008)
    assert meta.book_series == "Imaginary Cycle"
    assert meta.audiobook_duration_formatted == "11h 11m 00s"
    assert meta.genres == ["Teen & Young Adult", "Science Fiction & Fantasy", "Dystopian"]
    assert meta.keywords == ["teen", "young adult", "science fiction", "fantasy", "dystopian"]


@pytest.mark.asyncio
async def test_gather_book_prep_does_not_search_when_an_identifier_exists(tmp_path, monkeypatch):
    from src.google_books import google_books_manager
    from src.openlibrary import openlibrary_manager

    search = AsyncMock(return_value=None)
    monkeypatch.setattr(book_prep, "find_book_identifier", search)
    monkeypatch.setattr(google_books_manager, "search_by_isbn", AsyncMock(return_value=None))
    monkeypatch.setattr(openlibrary_manager, "search_by_isbn", AsyncMock(return_value=None))
    meta = Meta(isbn="9780000000026", title="Known", edit=True)

    await book_prep.gather_book_prep(meta, "book.epub", str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})

    assert search.await_count == 0


@pytest.mark.asyncio
async def test_narrator_falls_back_to_album_artist_or_read_by_note(tmp_path, monkeypatch):
    monkeypatch.setattr(book_prep, "find_book_identifier", AsyncMock(return_value=None))
    monkeypatch.setattr(book_prep, "get_audiobook_duration", AsyncMock(return_value=(0.0, "")))
    monkeypatch.setattr(book_prep, "get_audiobook_bitrate", AsyncMock(return_value=None))

    album_artist = Meta(
        audiobook=True,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Title": "The Invented Debt", "Performer": "Mira Example", "Album_Performer": "Tara Sample"}]}},
    )
    await book_prep.gather_book_prep(album_artist, "book.m4b", str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})
    assert (album_artist.author, album_artist.narrator) == ("Mira Example", "Tara Sample")

    same_person = Meta(
        audiobook=True,
        edit=True,
        mediainfo={
            "media": {
                "track": [
                    {"@type": "General", "Title": "Memoir", "Performer": "Mira Example", "Album_Performer": "Mira Example", "Comment": "Read by Mira Example. Unabridged."}
                ]
            }
        },
    )
    await book_prep.gather_book_prep(same_person, "book.m4b", str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})
    assert same_person.narrator == "Mira Example"

    junk_overview = Meta(
        audiobook=True,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Title": "Memoir", "Performer": "Mira Example", "Comment": "-", "Description": "A real synopsis."}]}},
    )
    await book_prep.gather_book_prep(junk_overview, "book.m4b", str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})
    assert junk_overview.overview == "A real synopsis."

    by_the_author = Meta(
        audiobook=True, edit=True, mediainfo={"media": {"track": [{"@type": "General", "Title": "Memoir", "Performer": "Mira Example", "Comment": "Read by the author."}]}}
    )
    await book_prep.gather_book_prep(by_the_author, "book.m4b", str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})
    assert by_the_author.narrator == "Mira Example"

    composer_wins = Meta(
        audiobook=True,
        edit=True,
        mediainfo={"media": {"track": [{"@type": "General", "Title": "Memoir", "Performer": "Mira Example", "Composer": "Real Reader", "Album_Performer": "Tara Sample"}]}},
    )
    await book_prep.gather_book_prep(composer_wins, "book.m4b", str(tmp_path), {"DEFAULT": {"google_books_api_key": "test"}})
    assert composer_wins.narrator == "Real Reader"


@pytest.mark.asyncio
async def test_audible_rip_atoms_and_bracketed_asin_are_read(tmp_path, monkeypatch):
    search = AsyncMock(return_value=None)
    monkeypatch.setattr(book_prep, "find_book_identifier", search)
    monkeypatch.setattr(book_prep, "get_audiobook_duration", AsyncMock(return_value=(0.0, "")))
    monkeypatch.setattr(book_prep, "get_audiobook_bitrate", AsyncMock(return_value=None))
    fetched = AsyncMock(return_value={"title": "Sunrise on the Reaping"})
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetched)

    atoms = Meta(
        audiobook=True,
        edit=True,
        mediainfo={
            "media": {
                "track": [
                    {
                        "@type": "General",
                        "Title": "Sunrise on the Reaping",
                        "Performer": "Suzanne Collins",
                        "extra": {"nrt": "Jefferson White", "LANGUAGE": "English", "AUDIBLE_ASIN": "B0D6PCZ98M"},
                    }
                ]
            }
        },
    )
    await book_prep.gather_book_prep(atoms, "book.m4b", str(tmp_path), {"DEFAULT": {}})
    assert (atoms.narrator, atoms.book_language, atoms.asin) == ("Jefferson White", "English", "B0D6PCZ98M")
    fetched.assert_awaited_once_with("B0D6PCZ98M", "audible.com", str(tmp_path))

    bracketed = Meta(audiobook=True, edit=True, mediainfo={}, basename_no_ext="Catching Fire (Hunger Games, Book Two) [B002V8L166]")
    await book_prep.gather_book_prep(bracketed, "Catching Fire [B002V8L166].m4b", str(tmp_path), {"DEFAULT": {}})
    assert bracketed.asin == "B002V8L166"
    assert search.await_count == 0


def test_openlibrary_catalog_tags_are_not_subjects():
    from src.openlibrary import _is_catalog_tag

    assert _is_catalog_tag("nyt:series_books=2010-08-21")
    assert _is_catalog_tag("collectionID:HungerGames")
    assert _is_catalog_tag("Accessible book")
    assert not _is_catalog_tag("Science fiction")
    assert not _is_catalog_tag("Young Adult")
    assert not _is_catalog_tag("Fiction: general")


@pytest.mark.asyncio
async def test_asin_from_another_marketplace_falls_back_to_the_title_search(tmp_path, monkeypatch):
    """A .com.au ASIN in the tags is unknown to audible.com; the search finds the .com listing of the same recording."""
    local_asin = "B0LOCAL123"

    async def fetch(asin, _domain, _base_dir):
        if asin == local_asin:
            return {"title": "Sunrise on the Reaping", "narrator": "Jefferson White", "genres": ["Teen & Young Adult", "Dystopian"], "runtime_minutes": 768}
        return None

    fetched = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetched)
    search = AsyncMock(return_value={"source": "audible", "asin": local_asin, "title": "Sunrise on the Reaping", "domain": "audible.com"})
    monkeypatch.setattr(book_prep, "find_book_identifier", search)
    monkeypatch.setattr(
        book_prep,
        "export_info",
        AsyncMock(
            return_value={
                "media": {"track": [{"@type": "General", "Title": "Sunrise on the Reaping", "Performer": "Suzanne Collins", "extra": {"AUDIBLE_ASIN": "B0D6PCZ98M"}}]}
            }
        ),
    )
    monkeypatch.setattr(book_prep, "get_audiobook_duration", AsyncMock(return_value=(768 * 60.0, "12h 48m 00s")))
    monkeypatch.setattr(book_prep, "get_audiobook_bitrate", AsyncMock(return_value=None))
    meta = Meta(audiobook=True, edit=False, mediainfo={}, basename_no_ext="Sunrise on the Reaping [B0D6PCZ98M]")

    await book_prep.gather_book_prep(meta, str(tmp_path / "book.m4b"), str(tmp_path), {"DEFAULT": {}})

    assert [call.args[0] for call in fetched.await_args_list] == ["B0D6PCZ98M", local_asin]
    assert search.await_count == 1
    assert meta.asin == local_asin
    assert meta.audible_url == f"https://www.audible.com/pd/{local_asin}"
    assert meta.genres == ["Teen & Young Adult", "Dystopian"]


@pytest.mark.asyncio
async def test_known_asin_is_fetched_once_and_skips_the_search(tmp_path, monkeypatch):
    fetched = AsyncMock(return_value={"title": "Known Book"})
    monkeypatch.setattr(book_prep, "fetch_audible_metadata", fetched)
    search = AsyncMock(return_value=None)
    monkeypatch.setattr(book_prep, "find_book_identifier", search)
    monkeypatch.setattr(book_prep, "export_info", AsyncMock(return_value={}))
    monkeypatch.setattr(book_prep, "get_audiobook_duration", AsyncMock(return_value=(0.0, "")))
    monkeypatch.setattr(book_prep, "get_audiobook_bitrate", AsyncMock(return_value=None))
    meta = Meta(audiobook=True, edit=False, mediainfo={}, asin=ASIN)

    await book_prep.gather_book_prep(meta, str(tmp_path / "book.m4b"), str(tmp_path), {"DEFAULT": {}})

    assert fetched.await_count == 1
    assert search.await_count == 0
    assert meta.title == "Known Book"


@pytest.mark.asyncio
async def test_openlibrary_isbn_lookup_adds_edition_language_and_narrator(tmp_path, monkeypatch):
    from src import openlibrary
    from src.openlibrary import OpenLibraryManager

    def respond(request):
        if request.url.path == "/api/books":
            return httpx.Response(
                200,
                json={
                    "ISBN:9780000000026": {
                        "details": {
                            "title": "The Invented Debt",
                            "authors": [{"name": "Mira Example"}],
                            "publishers": ["Fictional Audio"],
                            "publish_date": "2008",
                            "physical_format": "CD",
                            "languages": [{"key": "/languages/eng"}],
                            "contributors": [{"role": "Narrator", "name": "Tara Sample"}],
                        }
                    }
                },
            )
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(openlibrary.httpx, "AsyncClient", lambda **_kwargs: real_client(transport=httpx.MockTransport(respond)))

    data = await OpenLibraryManager().search_by_isbn("9780000000026", str(tmp_path))

    assert data["narrator"] == "Tara Sample"
    assert (data["book_language"], data["book_language_iso"]) == ("English", "eng")
    assert data["publisher"] == "Fictional Audio"
