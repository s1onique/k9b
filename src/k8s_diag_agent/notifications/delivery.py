from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..health.notifications import NotificationArtifact

DEFAULT_JOURNAL = "delivery-state.json"


def artifact_digest(artifact: NotificationArtifact) -> str:
    payload = json.dumps(artifact.to_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DeliveryJournal:
    def __init__(self, path: Path, records: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.path = path
        self.records: dict[str, dict[str, Any]] = {
            key: dict(value) for key, value in (records or {}).items()
        }

    @classmethod
    def load(cls, directory: Path, *, filename: str = DEFAULT_JOURNAL) -> DeliveryJournal:
        directory.mkdir(parents=True, exist_ok=True)
        journal_path = directory / filename
        records: dict[str, Mapping[str, Any]] = {}
        if journal_path.exists():
            try:
                raw = json.loads(journal_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw, Mapping) and "records" in raw and isinstance(raw["records"], Mapping):
                records = dict(raw["records"])
            elif isinstance(raw, Mapping):
                records = dict(raw)
        journal = cls(journal_path, records)
        journal._persist()
        return journal

    def is_delivered(self, artifact_name: str, digest: str) -> bool:
        entry = self.records.get(artifact_name)
        return bool(entry and entry.get("status") == "sent" and entry.get("hash") == digest)

    def needs_delivery(self, artifact_name: str, digest: str) -> bool:
        entry = self.records.get(artifact_name)
        if not entry:
            return True
        if entry.get("hash") != digest:
            return True
        return entry.get("status") != "sent"

    def record_result(
        self,
        artifact_name: str,
        digest: str,
        status: str,
        error: str | None = None,
    ) -> None:
        entry = self.records.get(artifact_name, {})
        entry["hash"] = digest
        entry["status"] = status
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        entry["last_attempted"] = datetime.now(UTC).isoformat()
        if error:
            entry["last_error"] = error
        elif "last_error" in entry:
            entry.pop("last_error")
        self.records[artifact_name] = entry
        self._persist()

    def _persist(self) -> None:
        payload = {"records": self.records}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
