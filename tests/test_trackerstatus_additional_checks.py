import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import trackerstatus
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


# Per-tracker code that TrackerStatusManager runs concurrently for every selected tracker.
_CONCURRENT_CHECKS = {"get_additional_checks", "check_banned_group"}


def _additional_check_functions() -> list[tuple[str, ast.AsyncFunctionDef | ast.FunctionDef]]:
    checks = []
    for path in [*sorted(Path("src/trackers").rglob("*.py")), Path("src/trackersetup.py")]:
        checks.extend(
            (f"{path}:{node.lineno}", node)
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name in _CONCURRENT_CHECKS
        )
    return checks


def test_tracker_checks_do_not_ask_their_own_override_question() -> None:
    """Trackers are checked concurrently; a check may not block stdin, and only the status manager asks "upload anyway?"."""
    offenders = []
    for location, func in _additional_check_functions():
        for node in ast.walk(func):
            blocking_prompt = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "cli_ui"
                and node.func.attr.startswith("ask_")
            )
            override_question = func.name == "get_additional_checks" and isinstance(node, ast.Constant) and isinstance(node.value, str) and "anyway?" in node.value
            if blocking_prompt or override_question:
                offenders.append(f"{location} line {node.lineno}")

    assert {func.name for _, func in _additional_check_functions()} == _CONCURRENT_CHECKS  # noqa: S101
    assert offenders == []  # noqa: S101
