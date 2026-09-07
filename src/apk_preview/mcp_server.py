from __future__ import annotations

import base64
import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import ImageContent, TextContent, ToolAnnotations

from .android import AndroidController
from .errors import PreviewError
from .session import Session, SessionStore

mcp = MCPServer(
    "apk-preview",
    instructions="Operate only dedicated Android emulators. Call apk_preview_doctor first. Never select a physical device.",
)
controller = AndroidController()
store = SessionStore()


def _session() -> Session:
    session = store.load()
    if not session:
        raise PreviewError("SESSION_REQUIRED", "Sessão ausente.", "Inicie sessão primeiro.")
    controller.assert_eligible(session.serial)
    return session


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
)
def apk_preview_doctor() -> dict[str, object]:
    """Diagnose Android SDK, Emulator, ADB, AVDs and connected devices."""
    return controller.doctor()


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
)
def apk_preview_list_avds() -> dict[str, object]:
    """List dedicated AVDs accepted by APK Preview."""
    return {"ok": True, "avds": controller.list_avds()}


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
)
def apk_preview_start_session(
    avd: str, visible: bool = True, timeout_seconds: int = 180
) -> dict[str, object]:
    """Start a dedicated AVD and save shared session."""
    serial = controller.start_avd(avd, visible=visible, timeout=max(30, min(timeout_seconds, 300)))
    store.save(Session(serial=serial, avd=avd))
    return {"ok": True, "serial": serial, "avd": avd}


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
)
def apk_preview_install_apk(apk_path: str) -> dict[str, object]:
    """Install or replace one local APK on active dedicated emulator."""
    return controller.install_apk(_session().serial, apk_path)


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
)
def apk_preview_list_apps() -> dict[str, object]:
    """List third-party packages installed in active emulator."""
    return {"ok": True, "packages": controller.list_apps(_session().serial)}


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
)
def apk_preview_launch_app(package: str) -> dict[str, object]:
    """Launch installed package main activity."""
    session = _session()
    controller.launch_app(session.serial, package)
    session.active_package = package
    store.save(session)
    return {"ok": True, "package": package}


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
)
def apk_preview_configure_display(
    profile: Literal["phone_compact", "phone_standard", "phone_large", "tablet"],
    orientation: Literal["portrait", "landscape"] = "portrait",
    theme: Literal["system", "light", "dark"] = "system",
    font_scale: float = 1.0,
) -> dict[str, object]:
    """Switch emulator screen profile, orientation, theme and font scale."""
    return {
        "ok": True,
        **controller.configure_display(_session().serial, profile, orientation, theme, font_scale),
    }


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
)
def apk_preview_inspect_screen(include_ui_tree: bool = True) -> list[TextContent | ImageContent]:
    """Return current emulator PNG and optional accessible UI tree."""
    session = _session()
    png = controller.capture(session.serial)
    metadata = {
        "ok": True,
        "serial": session.serial,
        "package": session.active_package,
        "ui_tree": controller.ui_tree(session.serial) if include_ui_tree else None,
    }
    return [
        TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False)),
        ImageContent(
            type="image", data=base64.b64encode(png).decode("ascii"), mime_type="image/png"
        ),
    ]


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
)
def apk_preview_interact(
    action: Literal["tap", "back", "home", "recents"],
    x: int | None = None,
    y: int | None = None,
) -> dict[str, object]:
    """Tap coordinates or press an allowed Android navigation key."""
    serial = _session().serial
    if action == "tap":
        if x is None or y is None:
            raise PreviewError(
                "COORDINATES_REQUIRED", "Tap exige x e y.", "Informe coordenadas da captura atual."
            )
        controller.tap(serial, x, y)
    else:
        controller.key(serial, action)
    return {"ok": True, "action": action}


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
)
def apk_preview_stop_session() -> dict[str, object]:
    """Stop active emulator without deleting AVD or artifacts."""
    session = _session()
    controller.stop(session.serial)
    store.clear()
    return {"ok": True, "stopped": session.serial}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
