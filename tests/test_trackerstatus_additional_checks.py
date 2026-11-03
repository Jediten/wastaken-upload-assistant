from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import manual_input, trackerstatus
from src.meta import Meta


class _Helper:
    prompted = False
    answer = True

    async def prompt_yes_no(self, _message: str, default: bool = False) -> bool:
        del default
        self.prompted = True
        return self.answer


@pytest.mark.asyncio
async def test_failed_additional_check_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False, isatty=lambda: False))

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(), helper)

    assert result is True  # noqa: S101
    assert helper.prompted is True  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_is_not_overridden_when_stdin_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=True))

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(), helper)

    assert result is False  # noqa: S101
    assert helper.prompted is False  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_is_not_overridden_when_prompt_reaches_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)

    async def prompt_yes_no(_message: str, default: bool = False) -> bool:
        del default
        helper.prompted = True
        raise EOFError

    monkeypatch.setattr(helper, "prompt_yes_no", prompt_yes_no)

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(), helper)

    assert result is False  # noqa: S101
    assert helper.prompted is True  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_is_skipped_in_unattended_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)

    async def check(_meta: Meta) -> bool:
        return False

    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), Meta(unattended=True), helper)

    assert result is False  # noqa: S101
    assert helper.prompted is False  # noqa: S101


@pytest.mark.asyncio
async def test_failed_additional_check_prompts_in_unattended_confirm_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False, isatty=lambda: False))

    async def check(_meta: Meta) -> bool:
        return False

    meta = Meta(unattended=True, unattended_confirm=True)
    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), meta, helper)

    assert result is True  # noqa: S101
    assert helper.prompted is True  # noqa: S101


@pytest.mark.asyncio
async def test_check_that_was_declined_is_not_asked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False, isatty=lambda: False))
    monkeypatch.setattr(manual_input, "prompt_in_thread", AsyncMock(return_value=False))

    async def check(meta: Meta) -> bool:
        return await manual_input.confirm_override(meta)

    meta = Meta()
    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), meta, helper)

    assert result is False  # noqa: S101
    assert helper.prompted is False  # noqa: S101


@pytest.mark.asyncio
async def test_hard_failure_after_an_accepted_override_is_still_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _Helper()
    monkeypatch.setattr(trackerstatus, "UploadHelper", lambda _config: helper)
    monkeypatch.setattr(trackerstatus.sys, "stdin", SimpleNamespace(closed=False, isatty=lambda: False))
    monkeypatch.setattr(manual_input, "prompt_in_thread", AsyncMock(return_value=True))

    async def check(meta: Meta) -> bool:
        await manual_input.confirm_override(meta)
        return False

    # A decline left over from an earlier check of this release must not suppress the question.
    meta = Meta(override_declined=True)
    result = await trackerstatus.TrackerStatusManager({})._run_additional_checks("TEST", SimpleNamespace(get_additional_checks=check), meta, helper)

    assert result is True  # noqa: S101
    assert helper.prompted is True  # noqa: S101
