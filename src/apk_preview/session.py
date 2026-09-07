from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Session:
    serial: str
    avd: str
    active_package: str | None = None


class SessionStore:
    def __init__(self, path: Path | None = None) -> None:
        base = Path(os.environ.get("LOCALAPPDATA", Path.cwd())) / "ApkPreview"
        self.path = path or base / "session.json"

    def save(self, session: Session) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def load(self) -> Session | None:
        if not self.path.is_file():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return Session(**data)

    def clear(self) -> None:
        if self.path.is_file():
            self.path.unlink()
