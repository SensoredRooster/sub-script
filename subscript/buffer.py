"""Rolling capture buffer.

v1 scaffold: treat a finished recording (or OBS replay buffer export) as the
source file. A later pass can replace this with a live ring buffer / OBS hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class BufferSource:
    path: Path
    buffer_seconds: int = 30

    def resolve(self) -> Path:
        if not self.path.exists():
            raise FileNotFoundError(f"Source video not found: {self.path}")
        return self.path
