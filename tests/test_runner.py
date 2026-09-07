from pathlib import Path

from apk_preview.runner import external_process_environment


def test_external_environment_removes_frozen_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    bundle = Path("C:/app/_internal")
    monkeypatch.setattr("apk_preview.runner.sys._MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("PATH", f"{bundle};C:/Windows/System32")
    monkeypatch.setenv("QT_PLUGIN_PATH", str(bundle / "PySide6" / "plugins"))

    environment = external_process_environment()

    assert environment["PATH"] == "C:/Windows/System32"
    assert "QT_PLUGIN_PATH" not in environment
