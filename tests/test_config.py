from pathlib import Path

from apk_preview.config import discover_android_tools


def test_discovers_sdk_from_android_home(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "platform-tools").mkdir()
    (tmp_path / "emulator").mkdir()
    (tmp_path / "platform-tools" / "adb.exe").write_bytes(b"")
    (tmp_path / "emulator" / "emulator.exe").write_bytes(b"")
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    tools = discover_android_tools()
    assert tools.sdk_root == tmp_path.resolve()
    assert tools.adb == (tmp_path / "platform-tools" / "adb.exe").resolve()
