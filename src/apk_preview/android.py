from __future__ import annotations

import hashlib
import re
import struct
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import AndroidTools, discover_android_tools
from .errors import PreviewError
from .runner import ProcessRunner

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ALLOWED_AVD_PREFIX = "ApkPreview_"
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")

DISPLAY_PROFILES: dict[str, tuple[int, int, int]] = {
    "phone_compact": (720, 1600, 320),
    "phone_standard": (1080, 2400, 420),
    "phone_large": (1440, 3120, 560),
    "tablet": (1600, 2560, 320),
}


@dataclass(frozen=True)
class Device:
    serial: str
    state: str


def parse_adb_devices(output: str) -> list[Device]:
    devices: list[Device] = []
    for line in output.splitlines()[1:]:
        columns = line.strip().split()
        if len(columns) >= 2:
            devices.append(Device(serial=columns[0], state=columns[1]))
    return devices


def validate_avd_name(name: str) -> str:
    if not name.startswith(ALLOWED_AVD_PREFIX) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise PreviewError(
            "AVD_NOT_ELIGIBLE",
            f"AVD deve começar por {ALLOWED_AVD_PREFIX}.",
            "Crie ou selecione AVD dedicado.",
        )
    return name


def validate_apk(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    if path.suffix.lower() != ".apk" or not path.is_file():
        raise PreviewError(
            "APK_INVALID", "APK local não encontrado.", "Selecione arquivo .apk existente."
        )
    return path


def png_dimensions(png: bytes) -> tuple[int, int]:
    if not png.startswith(PNG_SIGNATURE) or len(png) < 24:
        raise PreviewError("CAPTURE_FAILED", "Captura PNG inválida.", "Verifique tela do emulador.")
    return struct.unpack(">II", png[16:24])


class AndroidController:
    def __init__(
        self,
        tools: AndroidTools | None = None,
        runner: ProcessRunner | None = None,
    ) -> None:
        self.tools = tools or discover_android_tools()
        self.runner = runner or ProcessRunner()

    def _adb(self, *args: str, timeout: float = 30, check: bool = True) -> bytes:
        if not self.tools.adb:
            raise PreviewError(
                "ADB_NOT_FOUND", "ADB não encontrado.", "Instale Android Platform Tools."
            )
        return self.runner.run(self.tools.adb, list(args), timeout=timeout, check=check).stdout

    def _for_device(self, serial: str, *args: str, timeout: float = 30) -> bytes:
        self.assert_eligible(serial)
        return self._adb("-s", serial, *args, timeout=timeout)

    def doctor(self) -> dict[str, object]:
        avds: list[str] = []
        if self.tools.emulator:
            avds = self.list_avds()
        devices = self.devices() if self.tools.adb else []
        return {
            "ok": bool(self.tools.adb and self.tools.emulator),
            "sdk_root": str(self.tools.sdk_root) if self.tools.sdk_root else None,
            "adb": str(self.tools.adb) if self.tools.adb else None,
            "emulator": str(self.tools.emulator) if self.tools.emulator else None,
            "avds": avds,
            "devices": [device.__dict__ for device in devices],
        }

    def list_avds(self) -> list[str]:
        if not self.tools.emulator:
            raise PreviewError(
                "EMULATOR_NOT_FOUND", "Emulator não encontrado.", "Instale Android Emulator."
            )
        output = self.runner.run(self.tools.emulator, ["-list-avds"], timeout=10).text
        return [name for name in output.splitlines() if name.startswith(ALLOWED_AVD_PREFIX)]

    def devices(self) -> list[Device]:
        return parse_adb_devices(self._adb("devices", "-l").decode("utf-8", errors="replace"))

    def assert_eligible(self, serial: str) -> None:
        if not serial.startswith("emulator-"):
            raise PreviewError(
                "DEVICE_NOT_ELIGIBLE", "Aparelho físico bloqueado.", "Use AVD dedicado."
            )
        devices = {device.serial: device.state for device in self.devices()}
        if devices.get(serial) != "device":
            raise PreviewError("DEVICE_OFFLINE", "Emulador indisponível.", "Inicie nova sessão.")
        qemu = self._adb("-s", serial, "shell", "getprop", "ro.kernel.qemu").decode().strip()
        if qemu != "1":
            raise PreviewError(
                "DEVICE_NOT_ELIGIBLE", "QEMU não confirmado.", "Use Android Emulator."
            )

    def start_avd(self, avd: str, *, visible: bool = True, timeout: int = 180) -> str:
        validate_avd_name(avd)
        if avd not in self.list_avds():
            raise PreviewError(
                "AVD_NOT_FOUND", f"AVD {avd} não existe.", "Crie AVD pelo Android Studio."
            )
        assert self.tools.emulator is not None
        existing = self.devices()
        attach_deadline = time.monotonic() + timeout
        while time.monotonic() < attach_deadline:
            emulator_devices = [item for item in existing if item.serial.startswith("emulator-")]
            for device in emulator_devices:
                if device.state != "device":
                    continue
                running_avd = self._adb("-s", device.serial, "emu", "avd", "name").decode(
                    errors="replace"
                )
                if running_avd.splitlines()[0].strip() == avd:
                    self.assert_eligible(device.serial)
                    return device.serial
            if not emulator_devices or all(item.state == "device" for item in emulator_devices):
                break
            time.sleep(1)
            existing = self.devices()
        args = ["-avd", avd, "-no-boot-anim"]
        if not visible:
            args.append("-no-window")
        before = {device.serial for device in existing}
        self.runner.start(self.tools.emulator, args)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            candidates = [
                device.serial
                for device in self.devices()
                if device.state == "device"
                and device.serial.startswith("emulator-")
                and device.serial not in before
            ]
            for serial in candidates:
                booted = (
                    self._adb("-s", serial, "shell", "getprop", "sys.boot_completed")
                    .decode()
                    .strip()
                )
                if booted == "1":
                    self.assert_eligible(serial)
                    return serial
            time.sleep(1)
        raise PreviewError(
            "BOOT_TIMEOUT", "Android não concluiu boot.", "Tente cold boot no Android Studio."
        )

    def install_apk(self, serial: str, apk_value: str | Path) -> dict[str, object]:
        apk = validate_apk(apk_value)
        output = self._for_device(serial, "install", "-r", str(apk), timeout=300).decode(
            errors="replace"
        )
        return {
            "ok": "Success" in output,
            "apk": str(apk),
            "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
            "size_bytes": apk.stat().st_size,
        }

    def list_apps(self, serial: str) -> list[str]:
        output = self._for_device(serial, "shell", "pm", "list", "packages", "-3").decode(
            errors="replace"
        )
        return sorted(
            line.removeprefix("package:").strip() for line in output.splitlines() if line.strip()
        )

    def launch_app(self, serial: str, package: str) -> None:
        if not PACKAGE_RE.fullmatch(package):
            raise PreviewError(
                "PACKAGE_INVALID", "Package Android inválido.", "Selecione package listado."
            )
        self._for_device(
            serial,
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        )

    def capture(self, serial: str) -> bytes:
        self.assert_eligible(serial)
        remote = f"/data/local/tmp/apk-preview-{uuid.uuid4().hex}.png"
        with tempfile.TemporaryDirectory(prefix="apk-preview-") as temp_dir:
            local = Path(temp_dir) / "screen.png"
            try:
                self._adb(
                    "-s",
                    serial,
                    "shell",
                    "screencap",
                    "-p",
                    remote,
                    timeout=15,
                )
                self._adb("-s", serial, "pull", remote, str(local), timeout=30)
                png = local.read_bytes()
            finally:
                self._adb(
                    "-s",
                    serial,
                    "shell",
                    "rm",
                    "-f",
                    remote,
                    timeout=10,
                    check=False,
                )
        if not png.startswith(PNG_SIGNATURE):
            raise PreviewError(
                "CAPTURE_FAILED", "Captura PNG inválida.", "Verifique tela do emulador."
            )
        return png

    def ui_tree(self, serial: str) -> str:
        remote = "/sdcard/apk-preview-window.xml"
        self._for_device(serial, "shell", "uiautomator", "dump", remote, timeout=15)
        return self._for_device(serial, "exec-out", "cat", remote).decode(
            "utf-8", errors="replace"
        )[:25000]

    def configure_display(
        self,
        serial: str,
        profile: str,
        orientation: str = "portrait",
        theme: str = "system",
        font_scale: float = 1.0,
    ) -> dict[str, int | float | str]:
        if profile not in DISPLAY_PROFILES:
            raise PreviewError("PROFILE_INVALID", "Perfil desconhecido.", "Use perfil listado.")
        if orientation not in {"portrait", "landscape"}:
            raise PreviewError(
                "ORIENTATION_INVALID", "Orientação inválida.", "Use portrait ou landscape."
            )
        if theme not in {"system", "light", "dark"}:
            raise PreviewError("THEME_INVALID", "Tema inválido.", "Use system, light ou dark.")
        if not 0.85 <= font_scale <= 2.0:
            raise PreviewError(
                "FONT_SCALE_INVALID", "Escala de fonte fora do limite.", "Use 0.85 até 2.0."
            )
        width, height, density = DISPLAY_PROFILES[profile]
        self._for_device(serial, "shell", "wm", "size", f"{width}x{height}")
        self._for_device(serial, "shell", "wm", "density", str(density))
        rotation = "1" if orientation == "landscape" else "0"
        self._for_device(
            serial, "shell", "settings", "put", "system", "accelerometer_rotation", "0"
        )
        self._for_device(serial, "shell", "settings", "put", "system", "user_rotation", rotation)
        night_mode = {"system": "auto", "light": "no", "dark": "yes"}[theme]
        self._for_device(serial, "shell", "cmd", "uimode", "night", night_mode)
        self._for_device(
            serial, "shell", "settings", "put", "system", "font_scale", f"{font_scale:g}"
        )
        expected = (height, width) if orientation == "landscape" else (width, height)
        actual = (0, 0)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            actual = png_dimensions(self.capture(serial))
            if actual == expected:
                break
            time.sleep(0.4)
        if actual != expected:
            raise PreviewError(
                "DISPLAY_TIMEOUT",
                f"Tela permaneceu em {actual[0]}x{actual[1]}; esperado {expected[0]}x{expected[1]}.",
                "Tente novamente ou reinicie AVD.",
            )
        return {
            "profile": profile,
            "width": actual[0],
            "height": actual[1],
            "density": density,
            "orientation": orientation,
            "theme": theme,
            "font_scale": font_scale,
        }

    def key(self, serial: str, name: str) -> None:
        keys = {"back": "KEYCODE_BACK", "home": "KEYCODE_HOME", "recents": "KEYCODE_APP_SWITCH"}
        if name not in keys:
            raise PreviewError(
                "ACTION_INVALID", "Tecla não permitida.", "Use back, home ou recents."
            )
        self._for_device(serial, "shell", "input", "keyevent", keys[name])

    def tap(self, serial: str, x: int, y: int) -> None:
        if not (0 <= x <= 2560 and 0 <= y <= 2560):
            raise PreviewError(
                "COORDINATES_INVALID", "Coordenadas fora do limite.", "Inspecione tela novamente."
            )
        self._for_device(serial, "shell", "input", "tap", str(x), str(y))

    def stop(self, serial: str) -> None:
        self.assert_eligible(serial)
        self._adb("-s", serial, "emu", "kill", timeout=10)
