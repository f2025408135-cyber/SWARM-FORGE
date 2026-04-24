"""Mutex-guarded shared storage for multi-process Python architectures.

Provides lock-safe JSON file access and atomic directory writes using the
``filelock`` library, ensuring data integrity when up to 9+ independent
OS-level processes read/write a single ``MASTER_SCHEMA.json`` and a shared
``skills/`` directory concurrently.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable

from filelock import FileLock, Timeout

logger: logging.Logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: float = 30.0
_DIR_WATCHDOG_SETTLE: float = 0.5


# ---------------------------------------------------------------------------
# Synchronized JSON store
# ---------------------------------------------------------------------------

class SynchronizedJSONStore:
    """File-lock-protected JSON key-value store for multi-process access.

    Every public method acquires an exclusive lock before touching the file
    and releases it in a ``finally`` block so that the lock is never held
    indefinitely on exception.

    Parameters
    ----------
    file_path:
        Path to the shared JSON file (e.g. ``MASTER_SCHEMA.json``).
    timeout:
        Maximum seconds to wait for the lock before raising.
    """

    def __init__(
        self,
        file_path: str | Path,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._path: Path = Path(file_path)
        self._timeout: float = timeout
        self._lock: FileLock = FileLock(
            str(self._path) + ".lock",
            timeout=self._timeout,
        )

    # -- internal helpers ---------------------------------------------------

    def _initialize_empty_file(self) -> None:
        """Create an empty ``{}`` JSON file when the target does not exist.

        The creation is performed while holding the lock so that only one
        process wins the race to bootstrap the file.
        """
        if self._path.exists():
            return
        try:
            self._path.write_text(
                "{}\n",
                encoding="utf-8",
            )
            logger.info("Initialised empty store at %s", self._path)
        except OSError as exc:
            logger.error(
                "Failed to initialise store at %s: %s",
                self._path,
                exc,
            )

    # -- public API ---------------------------------------------------------

    def read(self) -> dict:
        """Acquire the lock and return the JSON contents as a dictionary.

        Returns
        -------
        dict
            The parsed JSON data, or an empty ``{}`` on any failure.
        """
        try:
            self._lock.acquire()
        except Timeout:
            logger.error(
                "Lock acquisition timed out (%.1fs) reading %s",
                self._timeout,
                self._path,
            )
            return {}

        try:
            self._initialize_empty_file()

            try:
                raw: str = self._path.read_text(encoding="utf-8")
                data: dict = json.loads(raw)
                if not isinstance(data, dict):
                    logger.warning(
                        "Store root is %s, not dict — wrapping in dict",
                        type(data).__name__,
                    )
                    data = {"_value": data}
                return data
            except json.JSONDecodeError as exc:
                logger.error(
                    "Corrupt JSON in %s: %s — returning empty dict",
                    self._path,
                    exc,
                )
                return {}
        finally:
            self._lock.release()

    def transaction(
        self,
        update_func: Callable[[dict], dict],
    ) -> bool:
        """Execute an **atomic** read-modify-write cycle.

        1. Acquire the lock.
        2. Read the current JSON state.
        3. Pass the state to *update_func* and collect the new state.
        4. Write the new state to a ``.tmp`` temp file.
        5. Atomically replace the target with the temp file.

        Parameters
        ----------
        update_func:
            A callable that receives the current dict and **must** return the
            modified dict to be persisted.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on any failure (logged).
        """
        try:
            self._lock.acquire()
        except Timeout:
            logger.error(
                "Lock acquisition timed out (%.1fs) for transaction on %s",
                self._timeout,
                self._path,
            )
            return False

        try:
            self._initialize_empty_file()

            # ---- read ------------------------------------------------------
            try:
                raw: str = self._path.read_text(encoding="utf-8")
                state: dict = json.loads(raw)
                if not isinstance(state, dict):
                    state = {"_value": state}
            except json.JSONDecodeError as exc:
                logger.error(
                    "Corrupt JSON in %s during transaction: %s",
                    self._path,
                    exc,
                )
                return False

            # ---- modify ----------------------------------------------------
            try:
                new_state: dict = update_func(state)
            except Exception as exc:
                logger.error(
                    "update_func raised %s: %s — aborting transaction",
                    type(exc).__name__,
                    exc,
                )
                return False

            if not isinstance(new_state, dict):
                logger.error(
                    "update_func returned %s, expected dict — aborting",
                    type(new_state).__name__,
                )
                return False

            # ---- write to temp then atomic swap ----------------------------
            tmp_path: Path = self._path.with_suffix(self._path.suffix + ".tmp")
            try:
                tmp_path.write_text(
                    json.dumps(new_state, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                tmp_path.replace(self._path)
            except OSError as exc:
                logger.error(
                    "Atomic write failed for %s: %s",
                    self._path,
                    exc,
                )
                # Best-effort cleanup of orphaned temp file.
                tmp_path.unlink(missing_ok=True)
                return False

            logger.debug("Transaction committed on %s", self._path)
            return True

        finally:
            self._lock.release()


# ---------------------------------------------------------------------------
# Synchronized skill writer
# ---------------------------------------------------------------------------

class SynchronizedSkillWriter:
    """Lock-protected writer for shared skill files across processes.

    Uses a **single directory-level lock** (``.skills_directory.lock``) so
    that any number of processes can safely create or overwrite individual
    ``.py`` files inside the same directory without corruption.

    Parameters
    ----------
    skills_dir:
        Path to the shared directory that holds skill modules.
    timeout:
        Maximum seconds to wait for the directory lock.
    """

    def __init__(
        self,
        skills_dir: str | Path,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._dir: Path = Path(skills_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock: FileLock = FileLock(
            str(self._dir / ".skills_directory.lock"),
            timeout=timeout,
        )

    def write_skill(
        self,
        filename: str,
        code: str,
    ) -> bool:
        """Atomically write *code* to a new (or existing) skill file.

        The write follows a temp-then-swap pattern:

        1. Acquire the directory lock.
        2. Write *code* to ``<filename>.tmp``.
        3. Atomically replace the target with the temp file.
        4. Sleep briefly so that external directory watchdogs (e.g. inotify,
           fswatch) can pick up the change before the lock is released.

        Parameters
        ----------
        filename:
            Name of the Python file (e.g. ``"recon_scan.py"``).
        code:
            Full source-code string to persist.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on any failure.
        """
        if not filename.endswith(".py"):
            logger.warning("Skill filename '%s' does not end in .py", filename)

        target: Path = self._dir / filename

        try:
            self._lock.acquire()
        except Timeout:
            logger.error(
                "Directory lock timed out writing skill '%s'",
                filename,
            )
            return False

        try:
            tmp_path: Path = target.with_suffix(target.suffix + ".tmp")
            try:
                tmp_path.write_text(code, encoding="utf-8")
                tmp_path.replace(target)
            except OSError as exc:
                logger.error(
                    "Atomic write failed for skill '%s': %s",
                    filename,
                    exc,
                )
                tmp_path.unlink(missing_ok=True)
                return False

            # Allow external directory watchdogs to settle.
            time.sleep(_DIR_WATCHDOG_SETTLE)

            logger.debug("Skill '%s' written to %s", filename, self._dir)
            return True

        finally:
            self._lock.release()
