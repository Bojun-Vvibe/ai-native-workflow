# Template: anomaly-alert daily cron

A small, composable scheduling recipe that runs an **anomaly check
plus a budget check** every morning, decides whether anything is
worth waking a human for, and (only then) pushes a notification —
either a macOS desktop banner, a webhook, or both.

The point: most days have nothing actionable. You want zero noise on
those days and a high-signal ping on the days that matter.

## Why this exists

Two adjacent failure modes at the operational layer:

1. **Daily reports nobody reads.** A markdown report dropped in
   `~/Reports/` every morning becomes wallpaper after week two. You
   stop opening it. The first real anomaly slips by because the
   filename looked like every other day's filename.
2. **Slack alerts that fire on every minor wobble.** A z-score
   threshold of `|z| ≥ 1.0` will page you most weekdays. After the
   third false positive, you mute the channel, and now real alerts
   are also muted.

The fix is composition, not a new tool:

- Run the **report** every day (cheap, idempotent).
- Run an **anomaly detector** over the same window. Use a
  conservative threshold (`|z| ≥ 2.0` or higher).
- Run a **budget check** with a meaningful daily ceiling.
- **Notify only when at least one of those two exits non-zero.**

This template wires those four pieces together using stock POSIX
tools, a `LaunchAgent` plist, and one bash script. No daemons, no
extra dependencies.

## When to use

- macOS daily-driver, single user, single laptop.
- You already produce a daily JSONL log of *something*
  (token usage, build minutes, request counts, error rates) and
  have a CLI that emits both a daily report and an anomaly verdict
  with a useful exit code.
- You want low-frequency, high-signal alerts: a banner once or
  twice a month, not a stream of yellow.

## When NOT to use

- Linux server. Use `systemd --user` timers and rewrite the wrapper
  in shell — the logic is portable, only the scheduler is not.
- You need sub-hour latency. Cron / `launchd` is the wrong layer for
  "alert within 60 seconds." Stream from the source instead.
- The metric is not stationary across the week (e.g. weekend traffic
  is structurally different from weekday). A flat trailing baseline
  will alert every Monday. Use the
  [`metric-baseline-rolling-window`](../metric-baseline-rolling-window/)
  template's seasonal-baseline section first, then come back here
  for the scheduling layer.

## Anti-patterns

- **Running the alert step every 15 minutes.** A z-score over a
  trailing baseline does not change meaningfully every 15 minutes,
  but the *cost* of recomputing it does. Once a day at a fixed time
  is enough for nearly all observability metrics that update at
  daily granularity.
- **Alerting on a single threshold across all metrics.** A request
  count can plausibly spike 3σ on launch day; an error rate at 3σ
  is a page. Either run two separate plists with two different
  thresholds, or compose multiple checks in the wrapper.
- **Posting to Slack from a personal LaunchAgent without a circuit
  breaker.** If the script ever loops, you'll publish dozens of
  identical alerts in seconds. The wrapper here writes a daily
  state file and refuses to re-alert for the same `(date, key)`.
- **Embedding the webhook URL in the plist.** The plist is checked
  into your dotfiles; the webhook is a credential. Read it from a
  file outside the repo (`~/.config/anomaly-alert/webhook` is the
  example here) and `chmod 600` it.

## Files

- `bin/run-anomaly-check.sh` — the wrapper. Runs the underlying
  CLI, captures exit codes, decides whether to notify, deduplicates
  per-day, writes a tiny audit log.
- `bin/notify-mac.sh` — desktop banner via `osascript` (no
  third-party install required).
- `bin/notify-webhook.sh` — POSTs a JSON payload to a webhook URL
  read from `~/.config/anomaly-alert/webhook`.
- `bin/install.sh` — symlinks the plist into
  `~/Library/LaunchAgents/`, then `launchctl bootstrap`s it.
- `bin/uninstall.sh` — `bootout`, then removes the symlink.
- `plist/com.example.anomaly-alert-daily.plist` — runs the wrapper
  at 09:05 local each day. Five minutes after the hour so it lands
  *after* any 09:00-scheduled report producer.
- `examples/sample-audit.log` — what the audit log looks like over
  a representative two-week stretch (mostly quiet, two real alerts).
- `examples/sample-banner.png.txt` — text description of the banner
  the user actually sees on an alert day. Plain text on purpose:
  this template ships no binary assets.

## How it works

```
                  +----------------------------+
                  | LaunchAgent at 09:05 daily |
                  +-------------+--------------+
                                |
                                v
                    bin/run-anomaly-check.sh
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
   <your-cli> anomalies                <your-cli> budget --check
   exit 0 (clean) | 2 (anomaly)        exit 0 (under) | 2 (breached)
              |                                   |
              +-----------------+-----------------+
                                |
                                v
                +----------------------------------+
                | If either exit==2 AND not yet    |
                | alerted today for this key:      |
                |   record in state file           |
                |   call notify-mac.sh and/or      |
                |        notify-webhook.sh         |
                +----------------------------------+
```

The wrapper has three exit codes of its own:

- `0` — checks ran, nothing to alert about.
- `1` — operational error (cli not found, log file missing).
  `launchd` will surface this in `last exit` so you notice.
- `2` — alert fired (or would have fired but was deduplicated).
  Useful for chaining into a higher-level health-check.

## Worked example

Pair this template with the `pew anomalies` and `pew budget`
subcommands of the [`pew-insights`](https://github.com/anomalyco/pew-insights)
CLI. The wrapper calls:

```bash
pew anomalies --baseline 7d --lookback 30d --threshold 2.0
pew budget    --check     --period day      --ceiling 50000
```

Either exiting non-zero triggers one banner (and one webhook POST,
if configured). The state file at
`~/.local/state/anomaly-alert/last.json` records:

```json
{"date": "2026-04-24", "keys_alerted": ["anomaly", "budget"]}
```

Subsequent runs that same calendar day are no-ops — the wrapper
reads `last.json` and exits `2` immediately if the key is already
recorded, *without* re-firing notifications.

To force a re-alert (debugging only):

```bash
rm ~/.local/state/anomaly-alert/last.json
launchctl kickstart -k gui/$(id -u)/com.example.anomaly-alert-daily
```

## Adapt this section

- Edit `Label` in the plist to your reverse-DNS namespace
  (e.g. `tld.you.anomaly-alert-daily`); the plist filename must
  match.
- Edit the time in `<key>StartCalendarInterval</key>`. Pick a
  weekday-morning time *after* whatever produces the source log.
- Edit `bin/run-anomaly-check.sh`:
  - `CLI_BIN` — path to your anomaly/budget CLI.
  - `ANOMALY_ARGS` and `BUDGET_ARGS` — your thresholds.
  - `NOTIFIERS` — comma-separated list, any of `mac`, `webhook`.
- If using webhook: write the URL to
  `~/.config/anomaly-alert/webhook` and `chmod 600` it. The
  wrapper refuses to read a world-readable webhook file.
- Run `./bin/install.sh` once. Re-run after editing the plist.

## Verifying it works

```bash
# Status
launchctl print gui/$(id -u)/com.example.anomaly-alert-daily | grep -E "state|last exit"

# Force a run
launchctl kickstart -k gui/$(id -u)/com.example.anomaly-alert-daily

# Read the audit log (one line per run, regardless of whether it alerted)
tail -n 20 ~/.local/state/anomaly-alert/audit.log

# Smoke-test the notifier in isolation (no scheduler involved)
./bin/notify-mac.sh "Title" "Body line"
```

## Safety notes

- The wrapper writes only to `~/.local/state/anomaly-alert/`. No
  global state. Removing that directory fully resets behavior.
- The wrapper never invokes `curl` against an unconfigured webhook.
  Without `~/.config/anomaly-alert/webhook`, only the local banner
  fires (if `mac` is in `NOTIFIERS`).
- The `launchctl bootout` in `bin/uninstall.sh` is idempotent;
  running it on a host where the agent was never installed exits 0.
- This template **does not** modify or read the user's source log.
  It only invokes a CLI you already trust.
