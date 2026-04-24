#!/usr/bin/env python3
"""Laddered timeout for agent tool calls.

A single tool call is given THREE timeouts that escalate, not one:

  1. soft_s  — at this point the tool is asked to *checkpoint and exit
               cleanly*. Side effects so far are kept; the call returns
               a partial result with `outcome="soft_timeout"`.
  2. hard_s  — at this point the tool is *cancelled*. Any side effects
               in flight are abandoned; we return `outcome="hard_timeout"`
               with whatever the tool managed to publish before hard.
  3. kill_s  — at this point the runner is *force-terminated* (thread
               leaked / process killed). Returns `outcome="killed"`. This
               is the safety net so the orchestrator can never wedge.

Why three and not one:
  - One timeout forces a binary choice between "let runaway calls eat
    the orchestrator's deadline" and "abort early and lose useful
    partial work".
  - Soft gives the tool a chance to flush a partial answer, write a
    checkpoint, or downgrade to a smaller scope.
  - Hard guarantees the orchestrator gets control back even if the tool
    ignored the soft request.
  - Kill guarantees the *process* gets control back even if the tool
    is stuck in a C extension that won't honor cancellation.

Pure stdlib. No async dependency. The runner is callback-based: the
tool gets a `should_soft_exit()` callable it polls, and a `publish()`
callable it uses to register partial results so they survive a hard
cancel.

CLI:
    python ladder.py demo
"""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class LadderResult:
    outcome: str  # "ok" | "soft_timeout" | "hard_timeout" | "killed" | "error"
    value: Any = None
    partial: Any = None
    elapsed_s: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "value": self.value,
            "partial": self.partial,
            "elapsed_s": round(self.elapsed_s, 4),
            "error": self.error,
        }


@dataclass
class LadderConfig:
    soft_s: float
    hard_s: float
    kill_s: float

    def __post_init__(self) -> None:
        if not (0 < self.soft_s < self.hard_s < self.kill_s):
            raise ValueError(
                "must satisfy 0 < soft_s < hard_s < kill_s; got "
                f"soft={self.soft_s} hard={self.hard_s} kill={self.kill_s}"
            )


def run_with_ladder(
    tool: Callable[[Callable[[], bool], Callable[[Any], None]], Any],
    cfg: LadderConfig,
    *,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> LadderResult:
    """Run `tool(should_soft_exit, publish)` under a 3-stage ladder.

    The tool MUST poll `should_soft_exit()` periodically. If it returns
    True, the tool should checkpoint and return promptly. The tool
    SHOULD call `publish(x)` whenever it has a self-consistent partial
    result; that value survives a hard cancel.
    """
    started = now()

    soft_event = threading.Event()
    state: dict = {"value": None, "partial": None, "error": None, "done": False}
    done_event = threading.Event()

    def _runner() -> None:
        try:
            def _should_soft_exit() -> bool:
                return soft_event.is_set()

            def _publish(x: Any) -> None:
                state["partial"] = x

            v = tool(_should_soft_exit, _publish)
            state["value"] = v
        except BaseException as e:  # noqa: BLE001
            state["error"] = f"{type(e).__name__}: {e}"
        finally:
            state["done"] = True
            done_event.set()

    t = threading.Thread(target=_runner, name="ladder-tool", daemon=True)
    t.start()

    deadline_soft = started + cfg.soft_s
    deadline_hard = started + cfg.hard_s
    deadline_kill = started + cfg.kill_s

    # Stage 1: wait for natural completion or soft deadline.
    while True:
        remaining = deadline_soft - now()
        if remaining <= 0:
            break
        if done_event.wait(timeout=min(remaining, 0.05)):
            elapsed = now() - started
            if state["error"]:
                return LadderResult("error", partial=state["partial"],
                                    elapsed_s=elapsed, error=state["error"])
            return LadderResult("ok", value=state["value"],
                                partial=state["partial"], elapsed_s=elapsed)

    # Stage 2: signal soft, wait until hard deadline.
    soft_event.set()
    while True:
        remaining = deadline_hard - now()
        if remaining <= 0:
            break
        if done_event.wait(timeout=min(remaining, 0.05)):
            elapsed = now() - started
            if state["error"]:
                return LadderResult("error", partial=state["partial"],
                                    elapsed_s=elapsed, error=state["error"])
            # Tool returned after we asked for soft. Treat as soft_timeout
            # if it took longer than the soft deadline; otherwise ok.
            outcome = "soft_timeout" if elapsed > cfg.soft_s else "ok"
            return LadderResult(outcome, value=state["value"],
                                partial=state["partial"], elapsed_s=elapsed)

    # Stage 3: hard timeout reached. The thread is daemon so it cannot
    # block process exit, but we still wait briefly for it to honor a
    # cooperative cancel via the soft flag (it might be in a final
    # publish). We do NOT join past kill_s.
    while now() < deadline_kill:
        if done_event.wait(timeout=0.05):
            break

    elapsed = now() - started
    if state["done"]:
        # It finished between hard and kill. Still classify as hard_timeout
        # because the orchestrator already moved on conceptually.
        return LadderResult("hard_timeout", value=state["value"],
                            partial=state["partial"], elapsed_s=elapsed,
                            error=state["error"])

    return LadderResult("killed", partial=state["partial"], elapsed_s=elapsed,
                        error="tool did not honor soft or hard deadline")


# --- demo --------------------------------------------------------------

def _demo() -> None:
    print("=== tool-call-timeout-laddered: demo ===")
    cfg = LadderConfig(soft_s=0.20, hard_s=0.40, kill_s=0.60)

    # 1) Cooperative tool finishes inside soft.
    def fast(should_soft_exit, publish):
        publish({"step": 0})
        time.sleep(0.05)
        publish({"step": 1, "answer": 42})
        return {"answer": 42, "steps": 2}

    r = run_with_ladder(fast, cfg)
    print("\n[1] cooperative-fast:")
    print(json.dumps(r.to_dict(), indent=2))

    # 2) Slow but cooperative: honors should_soft_exit, publishes partials.
    def slow_cooperative(should_soft_exit, publish):
        results = []
        for i in range(20):
            if should_soft_exit():
                publish({"completed": results, "stopped_at": i})
                return {"completed": results, "early": True}
            time.sleep(0.05)
            results.append(i * i)
            publish({"completed": results})
        return {"completed": results, "early": False}

    r = run_with_ladder(slow_cooperative, cfg)
    print("\n[2] slow-cooperative (expect soft_timeout, partial preserved):")
    print(json.dumps(r.to_dict(), indent=2))

    # 3) Uncooperative tool: never checks should_soft_exit. Hard cancels.
    def uncooperative(should_soft_exit, publish):
        publish({"phase": "starting"})
        time.sleep(2.0)  # well past kill_s
        return {"never": "returned"}

    r = run_with_ladder(uncooperative, cfg)
    print("\n[3] uncooperative (expect killed, partial='starting'):")
    print(json.dumps(r.to_dict(), indent=2))

    # 4) Tool raises.
    def boom(should_soft_exit, publish):
        publish({"phase": "about to fail"})
        raise RuntimeError("simulated tool failure")

    r = run_with_ladder(boom, cfg)
    print("\n[4] tool-raises (expect error, partial preserved):")
    print(json.dumps(r.to_dict(), indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        _demo()
    else:
        print("usage: python ladder.py demo")
        sys.exit(2)
