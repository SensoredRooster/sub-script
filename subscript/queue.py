from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Status = Literal["pending", "approved", "rejected", "uploaded"]


@dataclass
class QueueItem:
    id: str
    video_path: str
    source_path: str
    created_at: str
    status: Status = "pending"
    title: str = ""
    notes: str = ""
    trim_start: float | None = None
    trim_end: float | None = None
    edited_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueItem":
        fields = cls.__dataclass_fields__
        return cls(**{k: data[k] for k in fields if k in data})


class ReviewQueue:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"items": []})

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list(self, status: Status | None = None) -> list[QueueItem]:
        items = [QueueItem.from_dict(i) for i in self._read().get("items", [])]
        if status:
            items = [i for i in items if i.status == status]
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    def get(self, item_id: str) -> QueueItem | None:
        for item in self.list():
            if item.id == item_id:
                return item
        return None

    def enqueue(self, video_path: Path, source_path: Path, title: str = "") -> QueueItem:
        data = self._read()
        item = QueueItem(
            id=uuid.uuid4().hex[:12],
            video_path=str(video_path),
            source_path=str(source_path),
            created_at=datetime.now(timezone.utc).isoformat(),
            title=title or video_path.stem,
        )
        data.setdefault("items", []).append(item.to_dict())
        self._write(data)
        return item

    def update(self, item: QueueItem) -> QueueItem:
        data = self._read()
        items = data.get("items", [])
        for idx, raw in enumerate(items):
            if raw.get("id") == item.id:
                items[idx] = item.to_dict()
                break
        else:
            raise KeyError(item.id)
        data["items"] = items
        self._write(data)
        return item

    def set_status(self, item_id: str, status: Status, **fields: Any) -> QueueItem:
        item = self.get(item_id)
        if not item:
            raise KeyError(item_id)
        item.status = status
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        return self.update(item)
