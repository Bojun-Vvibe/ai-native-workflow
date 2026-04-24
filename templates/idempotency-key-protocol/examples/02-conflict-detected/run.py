"""Worked example 02: same key, different body ⇒ IdempotencyConflict."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bin"))

from idempotency_store import IdempotencyConflict, IdempotencyStore  # noqa: E402


def main() -> int:
    ticks = iter([1_700_000_000.0 + i for i in range(20)])
    clock = lambda: next(ticks)  # noqa: E731

    store_path = os.path.join(HERE, "store.json")
    if os.path.exists(store_path):
        os.remove(store_path)

    store = IdempotencyStore(path=store_path, clock=clock)
    sent = []

    def send_message(req):
        sent.append(req)
        return {"message_id": f"m-{len(sent)}"}

    key = "agent-B:m-3:s-1:send_message:notify-owner"

    body_v1 = {"to": "owner@example.invalid", "text": "build green"}
    body_v2 = {"to": "owner@example.invalid", "text": "build RED"}  # bug: agent regenerated text

    env = store.call(key, body_v1, send_message, ttl_seconds=600)
    print(f"first_call status={env['status']} message_id={env['response']['message_id']}")

    try:
        store.call(key, body_v2, send_message, ttl_seconds=600)
        print("second_call status=UNEXPECTED_OK")
        return 1
    except IdempotencyConflict as exc:
        d = exc.detail
        print(
            f"second_call status=conflict expected_hash={d['expected_request_hash'][:16]} "
            f"received_hash={d['received_request_hash'][:16]}"
        )
        print(f"side_effects_total={len(sent)} (would have been 2 without the protocol)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
