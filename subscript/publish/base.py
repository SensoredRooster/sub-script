"""Publisher interface + shared result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class NotConfiguredError(RuntimeError):
    """Raised when a platform live API is selected but credentials/config are missing."""


@dataclass
class PublishMeta:
    """Context passed to every publisher on Approve."""

    item_id: str
    title: str
    out_dir: Path
    approved_dir: Path
    description: str = ""
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    """Per-platform outcome (orchestrator never re-raises)."""

    platform: str
    ok: bool
    status: str  # uploaded | submitted | dry_run | manual | skipped | error | not_configured
    message: str = ""
    url: str | None = None
    folder: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def banner_line(self) -> str:
        bit = f"{self.platform}: {self.status}"
        if self.url:
            bit += f" — {self.url}"
        elif self.folder and self.status == "manual":
            bit += f" — {self.folder}"
        elif self.message:
            bit += f" — {self.message}"
        return bit


class Publisher(Protocol):
    """Real code path for one social platform."""

    name: str

    @property
    def enabled(self) -> bool:
        ...

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        ...
