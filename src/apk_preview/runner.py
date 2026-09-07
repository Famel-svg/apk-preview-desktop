from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .errors import PreviewError

_DLL_SEARCH_LOCK = threading.Lock()
_dll_search_sanitized = False
_PROCESS_BRIDGE = Path(__file__).resolve().parents[2] / "native" / "ProcessBridge.exe"


def external_process_command(executable: Path, args: Sequence[str]) -> list[str]:
    """Route Windows SDK tools through a clean native process boundary."""
    command = [str(executable), *args]
    if os.name == "nt" and _PROCESS_BRIDGE.is_file():
        return [str(_PROCESS_BRIDGE), *command]
    return command


def sanitize_frozen_windows_dll_search() -> None:
    """Restore standard DLL search after Qt UI libraries have loaded."""
    global _dll_search_sanitized
    if sys.platform != "win32":
        return

    import ctypes

    with _DLL_SEARCH_LOCK:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        set_dll_directory = kernel32.SetDllDirectoryW
        set_dll_directory.argtypes = [ctypes.c_wchar_p]
        set_dll_directory.restype = ctypes.c_int
        if not set_dll_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
        _dll_search_sanitized = True


@contextmanager
def external_dll_search() -> Generator[None, None, None]:
    """Temporarily undo PyInstaller's inherited Windows DLL directory."""
    bundle_value = getattr(sys, "_MEIPASS", None)
    if sys.platform != "win32":
        yield
        return

    if _dll_search_sanitized:
        with _DLL_SEARCH_LOCK:
            yield
        return

    if not bundle_value:
        yield
        return

    import ctypes

    with _DLL_SEARCH_LOCK:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        set_dll_directory = kernel32.SetDllDirectoryW
        set_dll_directory.argtypes = [ctypes.c_wchar_p]
        set_dll_directory.restype = ctypes.c_int
        if not set_dll_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            set_dll_directory(str(bundle_value))


def external_process_environment(executable: Path | None = None) -> dict[str, str]:
    """Remove frozen-app DLL/plugin paths before launching Android executables."""
    environment = os.environ.copy()
    if os.name == "nt" and executable is not None:
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        environment["PATH"] = os.pathsep.join(
            (str(executable.parent), str(windows / "System32"), str(windows))
        )
        for variable in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
            environment.pop(variable, None)
        return environment

    bundle_value = getattr(sys, "_MEIPASS", None)
    if not bundle_value:
        return environment

    bundle = os.path.normcase(os.path.abspath(str(bundle_value)))

    def belongs_to_bundle(value: str) -> bool:
        candidate = os.path.normcase(os.path.abspath(value))
        try:
            return os.path.commonpath((bundle, candidate)) == bundle
        except ValueError:
            return False

    path_parts = [
        value
        for value in environment.get("PATH", "").split(os.pathsep)
        if value and not belongs_to_bundle(value)
    ]
    environment["PATH"] = os.pathsep.join(path_parts)

    for variable in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        value = environment.get(variable)
        if value and belongs_to_bundle(value):
            environment.pop(variable, None)
    return environment


@dataclass(frozen=True)
class RunResult:
    stdout: bytes
    stderr: bytes
    returncode: int

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace").strip()


class ProcessRunner:
    def run(
        self,
        executable: Path,
        args: Sequence[str],
        *,
        timeout: float = 30,
        check: bool = True,
    ) -> RunResult:
        process: subprocess.Popen[bytes] | None = None
        try:
            with external_dll_search():
                process = subprocess.Popen(
                    external_process_command(executable, args),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    env=external_process_environment(executable),
                )
                stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                process.kill()
                process.communicate()
            raise PreviewError(
                "PROCESS_TIMEOUT", f"Comando excedeu {timeout:g}s.", "Tente novamente."
            ) from exc
        result = RunResult(stdout, stderr, process.returncode)
        if check and process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[-1200:]
            raise PreviewError("PROCESS_FAILED", detail or "Comando falhou.", "Abra diagnóstico.")
        return result

    def start(self, executable: Path, args: Sequence[str]) -> subprocess.Popen[bytes]:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with external_dll_search():
            return subprocess.Popen(
                external_process_command(executable, args),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=flags,
                env=external_process_environment(executable),
            )
