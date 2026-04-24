"""
OS-level mutex storage: thread- and process-safe JSON persistence via filelock.
"""
from __future__ import annotations

import json
import os
from typing import Any

import filelock


class SynchronizedJSONStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = filelock.FileLock(path + ".lock", timeout=30)

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not os.path.exists(self._path):
                return {}
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)

    def write(self, data: dict[str, Any]) -> None:
        with self._lock:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)

    def update(self, patch: dict[str, Any]) -> None:
        with self._lock:
            existing: dict[str, Any] = {}
            if os.path.exists(self._path):
                with open(self._path, encoding="utf-8") as fh:
                    existing = json.load(fh)
            existing.update(patch)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, indent=2)
