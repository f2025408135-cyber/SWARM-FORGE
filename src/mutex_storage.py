"""Mutex storage — thread- and process-safe JSON persistence via filelock.

Wraps a JSON file with an OS-level :class:`filelock.FileLock` so that
concurrent reads, writes, and updates from either multiple threads or
multiple processes are serialised deterministically. Used as the backing
store for Swarm-Forge run state in ``.swarmforge_state.json``.

Example:
    >>> store = SynchronizedJSONStore("state.json")
    >>> store.write({"status": "running"})
    >>> store.update({"nodes_completed": ["n1"]})
    >>> store.read()
    {'status': 'running', 'nodes_completed': ['n1']}

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Final

import filelock

logger: logging.Logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SEC: Final[int] = 30
LOCK_SUFFIX: Final[str] = ".lock"
JSON_INDENT: Final[int] = 2


class SynchronizedJSONStore:
    """File-backed JSON store with OS-level read/write/update synchronisation.

    Not safe to share across ``fork()`` without re-instantiating the lock.
    """

    def __init__(self, path: str) -> None:
        """Construct a store bound to *path* and its sidecar ``.lock`` file.

        Args:
            path: Filesystem path to the backing JSON file. A sibling file
                at ``{path}.lock`` is used for mutual exclusion.
        """
        self._path: str = path
        self._lock: filelock.FileLock = filelock.FileLock(
            path + LOCK_SUFFIX, timeout=LOCK_TIMEOUT_SEC
        )

    def read(self) -> dict[str, Any]:
        """Return the full JSON document, or ``{}`` if the file is missing.

        Returns:
            Parsed dict contents of the backing file, or an empty dict.
        """
        with self._lock:
            if not os.path.exists(self._path):
                return {}
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)

    def write(self, data: dict[str, Any]) -> None:
        """Overwrite the backing file with *data*.

        Args:
            data: JSON-serialisable mapping to persist.
        """
        with self._lock:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=JSON_INDENT)

    def update(self, patch: dict[str, Any]) -> None:
        """Shallow-merge *patch* into the existing document and persist.

        Args:
            patch: Keys to overlay on the existing document. Missing file
                is treated as an empty dict.
        """
        with self._lock:
            existing: dict[str, Any] = {}
            if os.path.exists(self._path):
                with open(self._path, encoding="utf-8") as fh:
                    existing = json.load(fh)
            existing.update(patch)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, indent=JSON_INDENT)
