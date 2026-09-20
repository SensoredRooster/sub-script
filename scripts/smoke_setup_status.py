"""Print setup checklist rows (no server)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subscript.setup_status import collect_setup_status  # noqa: E402


def main() -> None:
    payload = collect_setup_status()
    print(payload.get("summary", ""))
    for it in payload.get("items") or []:
        print(f"  [{it['status']:6}] {it['label']}: {it['detail']} — {it['fix']}")
    print(json.dumps(payload.get("counts") or {}, sort_keys=True))


if __name__ == "__main__":
    main()
