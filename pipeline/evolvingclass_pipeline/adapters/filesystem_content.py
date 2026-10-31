"""Filesystem blob store, keyed by content hash (dedupes identical bodies)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from evolvingclass_pipeline.ports import ContentStore


def canonical(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


class FilesystemContentStore(ContentStore):
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def put(self, body: Mapping[str, Any]) -> str:
        payload = canonical(body)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        ref = f"sha256:{digest}.json"
        path = self._root / f"{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
        return ref

    def get(self, storage_ref: str) -> Mapping[str, Any]:
        digest = storage_ref.removeprefix("sha256:").removesuffix(".json")
        return json.loads((self._root / f"{digest}.json").read_text())
