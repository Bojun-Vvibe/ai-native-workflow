"""Deterministic seed manager for agent runs.

Pure stdlib. One small dataclass + a few pure functions.

Why this exists:
    "Just pass seed=42 everywhere" is the bug. A run that reuses the
    SAME seed across every step couples the model's output for step 7
    to the noise sample chosen for step 1; resampling step 1 changes
    every downstream step. Worse, two parallel workers with the same
    seed produce correlated noise.

    The fix is *seed derivation*: pick ONE root seed for the whole
    mission, then derive a fresh per-(step, attempt, worker) seed from
    it via a deterministic hash. Replays of the same (root, step,
    attempt, worker) are byte-stable; sibling steps are independent.

Design rules:

1.  Root seed is a 256-bit hex string (64 chars). `from_env` /
    `from_random` cover the two real sources; `from_hex` is the
    replay-from-trace path. Construction validates length so a
    half-typed env var fails loudly.

2.  Derivation uses BLAKE2b-256 over a CANONICAL serialization of
    the (step_id, attempt, worker_id) tuple. Canonical means: the
    encoded bytes are fixed regardless of dict ordering or whitespace.

3.  Output of derive() is BOTH a 32-byte bytes value AND a 64-bit int
    (for `random.Random`) AND the full hex (for trace correlation).
    Callers grab whichever shape their downstream needs without
    rederiving.

4.  `random_for(...)` returns a fresh `random.Random` instance, NEVER
    touches `random.seed()` (mutating the global RNG is the most
    common source of "my tests pass alone but fail in CI" bugs).

5.  `attempt` is required, not defaulted. A retry of step 7 with the
    SAME attempt number must produce the SAME seed (idempotency); a
    retry under a NEW attempt number must produce a DIFFERENT seed
    (so two retries of the same step don't sample the same noise and
    fail in the same way for the same reason).

6.  `step_id` must be non-empty. An empty step id silently collides
    every derivation across the mission -- catch the typo at
    derivation time, not when debugging "why does every step look
    the same".

Composes with:
    - `agent-checkpoint-resume`: include `derive(...)` outputs in the
      step_begin record so a replay can verify byte-stability.
    - `prompt-fingerprinting`: feed `derive_hex(...)` into the prompt
      package as the `noise_seed` field so the fingerprint changes
      when the noise changes.
    - `tool-call-replay-log`: a recorded run replays byte-identical
      under the same root seed.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass


_ROOT_HEX_LEN = 64  # 256 bits hex
_DERIVE_DOMAIN = b"ai-native-workflow/deterministic-seed-manager/v1"


class SeedConfigError(ValueError):
    """Raised when a root seed or derivation input is malformed."""


@dataclass(frozen=True)
class DerivedSeed:
    """One derived seed in three formats.

    bytes32 : raw bytes for primitives that take a key
    int64   : non-negative 64-bit int for `random.Random(seed=...)`
    hex     : full 64-char hex string for trace correlation
    """

    bytes32: bytes
    int64: int
    hex: str

    def as_log_field(self) -> str:
        # Short prefix is enough for log queries; full hex is in trace.
        return self.hex[:16]


@dataclass(frozen=True)
class SeedManager:
    """Holds the root seed and derives child seeds from it.

    Construct via from_env / from_random / from_hex, never the
    raw constructor (which would let a caller smuggle in arbitrary
    state).
    """

    _root_hex: str

    @staticmethod
    def from_random() -> "SeedManager":
        """Mint a brand-new root from os-level entropy. Use for new runs."""
        return SeedManager(_root_hex=secrets.token_hex(32))

    @staticmethod
    def from_hex(hex_value: str) -> "SeedManager":
        """Replay a recorded root. Use for re-running a saved trace."""
        if not isinstance(hex_value, str):
            raise SeedConfigError(
                f"root seed must be str, got {type(hex_value).__name__}"
            )
        h = hex_value.strip().lower()
        if len(h) != _ROOT_HEX_LEN:
            raise SeedConfigError(
                f"root seed hex must be {_ROOT_HEX_LEN} chars (256 bits), "
                f"got {len(h)}"
            )
        try:
            int(h, 16)
        except ValueError as exc:
            raise SeedConfigError(
                f"root seed is not valid hex: {exc}"
            ) from exc
        return SeedManager(_root_hex=h)

    @staticmethod
    def from_env(var_name: str = "MISSION_ROOT_SEED") -> "SeedManager":
        """Read root from env -- prefer this in production for replay safety.

        Raises SeedConfigError if the env var is unset or malformed.
        Callers who want "use env if set, else mint" must do so explicitly.
        """
        raw = os.environ.get(var_name)
        if raw is None:
            raise SeedConfigError(
                f"environment variable {var_name!r} is unset; "
                f"call from_random() to mint a fresh root or set "
                f"{var_name} to a 64-char hex string for replay"
            )
        return SeedManager.from_hex(raw)

    # -- public surface -----------------------------------------------------

    def root_hex(self) -> str:
        return self._root_hex

    def derive(
        self,
        *,
        step_id: str,
        attempt: int,
        worker_id: str = "",
    ) -> DerivedSeed:
        """Derive a child seed for one (step, attempt, worker) tuple.

        Pure / deterministic / idempotent: same inputs -> identical output
        across processes, machines, and Python versions (BLAKE2b is part
        of stdlib hashlib and stable).
        """
        if not isinstance(step_id, str) or step_id == "":
            raise SeedConfigError("step_id must be a non-empty string")
        if not isinstance(attempt, int) or isinstance(attempt, bool):
            raise SeedConfigError(
                f"attempt must be int (not bool), got {type(attempt).__name__}"
            )
        if attempt < 0:
            raise SeedConfigError(f"attempt must be >= 0, got {attempt}")
        if not isinstance(worker_id, str):
            raise SeedConfigError(
                f"worker_id must be str, got {type(worker_id).__name__}"
            )

        canonical = json.dumps(
            {
                "step_id": step_id,
                "attempt": attempt,
                "worker_id": worker_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        h = hashlib.blake2b(
            digest_size=32,
            key=bytes.fromhex(self._root_hex),
            person=_DERIVE_DOMAIN[:16],
        )
        h.update(canonical)
        digest = h.digest()
        # Lower 64 bits as a non-negative int for random.Random.
        int64 = int.from_bytes(digest[:8], "big", signed=False)
        return DerivedSeed(bytes32=digest, int64=int64, hex=digest.hex())

    def random_for(
        self,
        *,
        step_id: str,
        attempt: int,
        worker_id: str = "",
    ):
        """Return a fresh `random.Random` seeded from the derivation.

        NEVER touches the global `random` module. Two callers can
        pull a `random_for(...)` at the same time without interfering.
        """
        import random as _random

        ds = self.derive(step_id=step_id, attempt=attempt, worker_id=worker_id)
        return _random.Random(ds.int64)
