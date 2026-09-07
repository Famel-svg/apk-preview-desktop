from pathlib import Path

import pytest

from apk_preview.android import (
    PNG_SIGNATURE,
    parse_adb_devices,
    png_dimensions,
    validate_apk,
    validate_avd_name,
)
from apk_preview.errors import PreviewError


def test_parse_adb_devices() -> None:
    output = "List of devices attached\nemulator-5554 device product:sdk model:sdk\nUSB123 unauthorized\n"
    devices = parse_adb_devices(output)
    assert [(item.serial, item.state) for item in devices] == [
        ("emulator-5554", "device"),
        ("USB123", "unauthorized"),
    ]


def test_parse_booting_emulator_as_offline() -> None:
    output = "List of devices attached\nemulator-5554 offline transport_id:1\n"
    assert parse_adb_devices(output)[0].state == "offline"


@pytest.mark.parametrize("name", ["Pixel_9", "ApkPreview_../bad", "ApkPreview_ bad"])
def test_rejects_unsafe_avd_names(name: str) -> None:
    with pytest.raises(PreviewError):
        validate_avd_name(name)


def test_accepts_dedicated_avd() -> None:
    assert validate_avd_name("ApkPreview_Phone_API36") == "ApkPreview_Phone_API36"


def test_validate_apk(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"apk")
    assert validate_apk(apk) == apk.resolve()


def test_rejects_non_apk(tmp_path: Path) -> None:
    file = tmp_path / "demo.txt"
    file.write_text("x")
    with pytest.raises(PreviewError):
        validate_apk(file)


def test_reads_png_dimensions() -> None:
    png = PNG_SIGNATURE + b"\x00" * 8 + (720).to_bytes(4, "big") + (1600).to_bytes(4, "big")
    assert png_dimensions(png) == (720, 1600)
