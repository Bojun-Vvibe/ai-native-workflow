"""Worked example for agent-loop-iteration-cap.

Four parts:
  1. Healthy loop converges in 4 iterations -> outcome='done'.
  2. Spinning loop trips stuck detector after 2 identical fingerprints,
     with cooldowns applied -> outcome='stuck'.
  3. Slow but progressing loop exhausts max_iterations -> outcome='exhausted'.
  4. Long loop trips wall-clock deadline -> outcome='expired'.

Uses a fake clock + recording sleep so the test runs in milliseconds while
exercising the full cooldown math.
"""

from __future__ import annotations

from iteration_cap import StepResult, run_with_cap


class FakeClock:
    def __init__(self, t0: float = 1000.0):
        self.t = t0
        self.sleep_log: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleep_log.append(s)
        self.t += s


def main() -> int:
    print("=" * 70)
    print("PART 1: healthy converging loop")
    print("=" * 70)
    clk = FakeClock()

    def healthy_step(state: dict) -> StepResult:
        clk.t += 0.1  # each step takes 100ms of "wall clock"
        new_state = {"counter": state["counter"] + 1}
        return StepResult(state=new_state, done=new_state["counter"] >= 4, observable=new_state["counter"])

    out = run_with_cap(
        initial_state={"counter": 0},
        step=healthy_step,
        fingerprint=lambda s: f"counter={s['counter']}",
        max_iterations=10,
        now=clk.now,
        sleep=clk.sleep,
    )
    print(f"  outcome={out.outcome} iterations={out.iterations} final={out.final_state}")
    print(f"  cooldowns_applied={out.cooldowns_applied} total_cooldown_s={out.total_cooldown_s}")
    print(f"  fingerprints={out.fingerprints}")
    assert out.outcome == "done" and out.iterations == 4 and out.cooldowns_applied == 0

    print()
    print("=" * 70)
    print("PART 2: spinning loop -> stuck (with cooldowns)")
    print("=" * 70)
    clk = FakeClock()

    def spinning_step(state: dict) -> StepResult:
        # Agent makes the same observation forever — fingerprint never changes.
        return StepResult(state={"obs": "tool returned []"}, done=False)

    out = run_with_cap(
        initial_state={"obs": "init"},
        step=spinning_step,
        fingerprint=lambda s: s["obs"],
        max_iterations=10,
        stuck_threshold=2,
        cooldown_after=1,
        base_cooldown_s=0.5,
        max_cooldown_s=4.0,
        now=clk.now,
        sleep=clk.sleep,
    )
    print(f"  outcome={out.outcome} iterations={out.iterations}")
    print(f"  stuck_fingerprint={out.stuck_fingerprint!r}")
    print(f"  cooldowns_applied={out.cooldowns_applied} total_cooldown_s={out.total_cooldown_s}")
    print(f"  sleep_log={clk.sleep_log}")
    assert out.outcome == "stuck"
    # iter 1: fingerprints=['tool returned []'] -> len<2, no stuck. consecutive=0.
    # iter 2: fingerprints=['tool returned []','tool returned []'] -> stuck trips. Before
    #          iter 2 cooldown_after=1 was satisfied (consecutive_no_progress=0, threshold=1?)
    # Actually: cooldown trigger is `consecutive_no_progress >= cooldown_after`. After
    # iter 1, consecutive_no_progress=0 (only one fingerprint), so iter 2 has no cooldown.
    # Stuck fires at end of iter 2. So 0 cooldowns. Adjust expectation:
    assert out.iterations == 2

    print()
    print("=" * 70)
    print("PART 2b: slowly-spinning loop with cooldowns visible")
    print("=" * 70)
    # Force a longer stuck threshold so we see cooldowns kick in.
    clk = FakeClock()
    out2 = run_with_cap(
        initial_state={"obs": "init"},
        step=spinning_step,
        fingerprint=lambda s: s["obs"],
        max_iterations=10,
        stuck_threshold=5,        # need 5 identical fingerprints before stuck
        cooldown_after=1,         # but cooldown after 1 no-progress
        base_cooldown_s=0.5,
        max_cooldown_s=4.0,
        now=clk.now,
        sleep=clk.sleep,
    )
    print(f"  outcome={out2.outcome} iterations={out2.iterations}")
    print(f"  cooldowns_applied={out2.cooldowns_applied} total_cooldown_s={out2.total_cooldown_s}")
    print(f"  sleep_log={clk.sleep_log}  (should be exponential: 0.5, 1.0, 2.0, ...)")
    assert out2.outcome == "stuck" and out2.iterations == 5 and out2.cooldowns_applied >= 2

    print()
    print("=" * 70)
    print("PART 3: progressing loop hits max_iterations -> exhausted")
    print("=" * 70)
    clk = FakeClock()
    counter = {"n": 0}

    def progressing_step(state: dict) -> StepResult:
        counter["n"] += 1
        # Each iteration produces a NEW fingerprint, so never stuck — but never done either.
        return StepResult(state={"step": counter["n"]}, done=False)

    out = run_with_cap(
        initial_state={"step": 0},
        step=progressing_step,
        fingerprint=lambda s: f"step={s['step']}",
        max_iterations=5,
        base_cooldown_s=0.0,  # disable cooldown to keep this case clean
        now=clk.now,
        sleep=clk.sleep,
    )
    print(f"  outcome={out.outcome} iterations={out.iterations} final={out.final_state}")
    print(f"  unique_fingerprints={len(set(out.fingerprints))}/{len(out.fingerprints)}")
    assert out.outcome == "exhausted" and out.iterations == 5

    print()
    print("=" * 70)
    print("PART 4: deadline trips -> expired")
    print("=" * 70)
    clk = FakeClock(t0=1000.0)

    def slow_step(state: dict) -> StepResult:
        clk.t += 2.0  # each step burns 2s of wall clock
        return StepResult(state={"step": state["step"] + 1}, done=False)

    out = run_with_cap(
        initial_state={"step": 0},
        step=slow_step,
        fingerprint=lambda s: f"step={s['step']}",
        max_iterations=100,
        deadline_at=1005.0,  # 5s budget; should fit ~2 steps then expire
        base_cooldown_s=0.0,
        now=clk.now,
        sleep=clk.sleep,
    )
    print(f"  outcome={out.outcome} iterations={out.iterations} final={out.final_state}")
    print(f"  clk.t at exit = {clk.t}")
    assert out.outcome == "expired"

    print()
    print("ALL PARTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
