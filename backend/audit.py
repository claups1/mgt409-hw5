"""Append-only audit trail: one record per agent-loop step.

output/audit_trail.json is a JSON list. Each new record is added to the end and
the file is rewritten atomically (temp file, then replace), so a crash can't
leave half a file and earlier runs are never wiped. If the existing file isn't
valid JSON we stop rather than overwrite it.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import AUDIT_PATH, AUDIT_TEXT_LIMIT
from models import AuditRecord


def clip(value: Any, limit: int = AUDIT_TEXT_LIMIT) -> Any:
    """Shorten long strings (recursively) so one tool result can't bloat the trail."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"... (+{len(value) - limit} chars)"
    if isinstance(value, dict):
        return {k: clip(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clip(v, limit) for v in value]
    return value


class AuditTrail:
    def __init__(self, path: Path = AUDIT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{self.path} is not a JSON list; refusing to overwrite it.")
        return data

    def count(self) -> int:
        return len(self.load())

    def append(self, record: AuditRecord) -> None:
        records = self.load()
        records.append(record.model_dump(mode="json"))
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        for attempt in range(5):  # OneDrive can briefly lock the file while syncing
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
