from __future__ import annotations


class PreviewError(RuntimeError):
    """Expected, actionable application error."""

    def __init__(self, code: str, message: str, next_step: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_step = next_step

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "ok": False,
            "code": self.code,
            "message": self.message,
            "next_step": self.next_step,
        }
