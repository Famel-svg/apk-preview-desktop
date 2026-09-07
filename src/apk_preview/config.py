from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AndroidTools:
    sdk_root: Path | None
    adb: Path | None
    emulator: Path | None


def _valid_executable(path: Path | None) -> Path | None:
    return path.resolve() if path and path.is_file() else None


def discover_android_tools() -> AndroidTools:
    candidates: list[Path] = []
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if value := os.environ.get(variable):
            candidates.append(Path(value).expanduser())
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(local_app_data) / "Android" / "Sdk")

    sdk_root = next((path.resolve() for path in candidates if path.is_dir()), None)
    adb = _valid_executable(sdk_root / "platform-tools" / "adb.exe") if sdk_root else None
    emulator = _valid_executable(sdk_root / "emulator" / "emulator.exe") if sdk_root else None

    adb_from_path = shutil.which("adb")
    emulator_from_path = shutil.which("emulator")
    adb = adb or (_valid_executable(Path(adb_from_path)) if adb_from_path else None)
    emulator = emulator or (
        _valid_executable(Path(emulator_from_path)) if emulator_from_path else None
    )
    return AndroidTools(sdk_root=sdk_root, adb=adb, emulator=emulator)
