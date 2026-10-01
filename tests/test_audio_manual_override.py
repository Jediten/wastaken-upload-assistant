import pytest

from src.args import Args
from src.audio import AudioManager
from src.meta import Meta


@pytest.mark.parametrize(
    ("detected", "manual", "expected"),
    [
        ("DD+ EX 7.1", "DD+ 7.1", "DD+ 7.1"),
        ("DD+ EX 7.1", None, "DD+ EX 7.1"),
        ("DD+ EX 7.1", "   ", "DD+ EX 7.1"),
        ("Dual-Audio DD+ EX 7.1", "DD+ 7.1", "Dual-Audio DD+ 7.1"),
        ("MULTI DTS-HD MA 5.1", "TrueHD 7.1 Atmos", "MULTI TrueHD 7.1 Atmos"),
        ("Dubbed DD 5.1", "DD 2.0", "Dubbed DD 2.0"),
        ("Dual-Audio DD+ EX 7.1", "DD+  7.1", "Dual-Audio DD+ 7.1"),
        ("Dual-Audio DD+ 5.1", "Dubbed DD+ 5.1", "Dubbed DD+ 5.1"),
    ],
)
def test_apply_manual_audio(detected: str, manual: str | None, expected: str) -> None:
    assert AudioManager.apply_manual_audio(detected, manual) == expected  # noqa: S101


def test_audio_cli_flag_sets_manual_audio() -> None:
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(["--webui", "--audio", "DD+ 7.1"], Meta())

    assert meta.manual_audio == "DD+ 7.1"  # noqa: S101


def test_audio_spectrogram_flag_still_parses() -> None:
    meta, _, _ = Args({"DEFAULT": {"screens": 1}}).parse(["--webui", "--audio-spectrogram"], Meta())

    assert meta.audio_spectrogram is True  # noqa: S101
    assert meta.manual_audio is None  # noqa: S101
