"""cross-tick-state-handoff — file-locked JSON state envelope.

Pass partial work between successive ticks of an autonomous dispatcher
(or any cron-like loop) without losing or double-applying state.

Why a dedicated template instead of "just write JSON":

  - `json.dump` to the same path is non-atomic. A crash mid-write
    leaves a truncated file that the next tick fails to parse.
  - Two ticks overlapping (the previous one ran long) will race on
    the file. We need a lock that survives across processes.
  - The reader needs to know whether the envelope was written by an
    older incompatible schema. We carry a `schema_version` and refuse
    to load mismatches.
  - Each tick should see *exactly* the state the previous tick
    committed — no partial updates, no stale snapshots — and should
    be able to commit the next state in a single atomic step.

The envelope file lives at a caller-chosen path (typically under
`~/.local/state/<app>/handoff.json`). Lock acquisition is via
`fcntl.flock` on a sibling `.lock` file, which is portable across
POSIX. Atomic write is via `os.replace` after writing to a temp file
in the same directory.

Public API:

  HandoffStore(path, schema_version) — construct
  store.load() -> dict | None — return committed state, or None first time
  with store.transaction() as state: ... — read-modify-write under lock
  store.snapshot() -> dict | None — read without taking write lock

The transaction context manager yields a mutable dict pre-loaded
with the committed state (or `{}` on first run). Mutations to that
dict are atomically committed on `__exit__` if no exception fired;
on exception the file is left untouched and the exception propagates.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import time
from typing import Any, Iterator


class HandoffError(Exception):
    """Raised for envelope schema/version mismatch or corruption."""


class HandoffStore:
    SCHEMA_KEY = "_schema"
    META_KEY = "_meta"

    def __init__(self, path: str, schema_version: int) -> None:
        if schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        self.path = os.path.abspath(path)
        self.schema_version = schema_version
        self.lock_path = self.path + ".lock"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    # ---- read paths ----

    def snapshot(self) -> dict[str, Any] | None:
        """Return the committed state without taking the write lock.

        Useful for read-only inspection. Returns None if no envelope
        has been committed yet.
        """
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        return self._unwrap(envelope)

    def load(self) -> dict[str, Any] | None:
        """Alias for snapshot() — kept for symmetry with .commit()."""
        return self.snapshot()

    # ---- write paths ----

    @contextlib.contextmanager
    def transaction(self, *, lock_timeout_s: float = 5.0) -> Iterator[dict[str, Any]]:
        """Acquire the write lock, yield mutable state, atomically commit.

        On exception inside the `with` block, the envelope is left
        untouched and the exception propagates.

        Raises HandoffError if the lock cannot be acquired within
        `lock_timeout_s`.
        """
        lock_fd = self._acquire_lock(lock_timeout_s)
        try:
            state = self.snapshot() or {}
            yield state
            self._commit(state)
        finally:
            self._release_lock(lock_fd)

    # ---- internals ----

    def _acquire_lock(self, timeout_s: float) -> int:
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise HandoffError(
                        f"could not acquire lock on {self.lock_path} "
                        f"within {timeout_s}s"
                    )
                time.sleep(0.05)

    def _release_lock(self, fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _commit(self, state: dict[str, Any]) -> None:
        envelope = {
            self.SCHEMA_KEY: self.schema_version,
            self.META_KEY: {
                "committed_at": time.time(),
                "pid": os.getpid(),
            },
            "state": state,
        }
        directory = os.path.dirname(self.path)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".handoff.", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(envelope, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise

    def _unwrap(self, envelope: Any) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            raise HandoffError(f"envelope at {self.path} is not a JSON object")
        version = envelope.get(self.SCHEMA_KEY)
        if version != self.schema_version:
            raise HandoffError(
                f"envelope schema version {version!r} does not match "
                f"expected {self.schema_version!r}; refusing to load. "
                f"Migrate the envelope or bump the reader."
            )
        state = envelope.get("state")
        if not isinstance(state, dict):
            raise HandoffError("envelope.state is missing or not an object")
        return state
