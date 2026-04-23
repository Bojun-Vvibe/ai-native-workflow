# Template: macOS launchd recipe for daily token-budget reports

A `LaunchAgent` `.plist` plus a small wrapper script that runs your
[`token-budget-tracker`](../token-budget-tracker/) report **once per
day** at a fixed local time, writes the markdown report to a known
path, and (optionally) opens it in your default markdown viewer.

The point: daily cost visibility without depending on a server, a
cron daemon, or remembering to run a command.

## Why this exists

A weekly cost report you have to remember to run is a cost report
that exists for the first two weeks. After that, you stop running
it, and your "we're tracking spend" claim is fiction.

`launchd` runs whether you remember or not. macOS reliably wakes
the agent at the configured time even on battery, even on
clamshell, as long as the user is logged in. A daily report becomes
a real habit because it shows up — usually as a fresh file in
`~/Reports/` or a Slack/email push.

## When to use

- macOS daily-driver, single user.
- You already have `token-budget-tracker` (or any script that emits
  a markdown daily report from a JSONL log) and want it on a timer.
- You want **per-user** scheduling. `LaunchAgent` is per-user;
  `LaunchDaemon` is system-wide and overkill for a personal report.

## When NOT to use

- Linux server. Use `systemd --user` or a cron entry.
- The report depends on remote state (e.g., it must SSH into a
  build box). Put it on the build box, not your laptop.
- You want **multi-user** sharing. Push the report to a shared
  channel from a server, not a personal LaunchAgent.

## Anti-patterns

- **Running every minute "just in case."** `StartInterval: 60` is a
  battery-drain footgun and produces N duplicates per day. Use
  `StartCalendarInterval` for "once at 09:00".
- **No `StandardErrorPath`.** When the script fails silently, you
  get no report and no error. Always log stderr to a file.
- **Pointing the script at a path with spaces and not quoting.**
  `~/My Documents/report.md` will silently fail to write.
- **Hardcoding `/usr/local/bin/python3`.** Use the absolute path
  to the python you actually want (`which python3` first), or
  use a venv with an absolute interpreter path. `launchd` does
  not source your shell rc files — your `PATH` is minimal.
- **Forgetting to `bootstrap` after editing the plist.** Edits
  don't apply until you `bootout` and `bootstrap` again. You'll
  spend an hour debugging an old version of the script.
- **Storing the plist outside `~/Library/LaunchAgents/`.** It
  won't auto-load on login. Symlinking from a repo is fine; the
  link must live in `~/Library/LaunchAgents/`.

## Files

- `plist/com.example.token-budget-daily.plist` — the LaunchAgent
  definition. Runs at 09:00 local every day.
- `bin/run-daily-report.sh` — the wrapper script. Resolves
  python, runs the report, writes to `~/Reports/token-budget/`,
  rotates files older than 90 days.
- `bin/install.sh` — copies/symlinks the plist into
  `~/Library/LaunchAgents/`, then `launchctl bootstrap`s it.
- `bin/uninstall.sh` — `bootout`, then removes the symlink.
- `examples/sample-report.md` — what one day's report looks like.
- `examples/sample-stderr.log` — what successful + failure
  invocations look like in the stderr log.

## Worked example

```bash
cd templates/token-budget-launchd
./bin/install.sh
# Wait until 09:00 next morning.
ls ~/Reports/token-budget/
# 2026-04-24.md
# 2026-04-23.md
```

To test immediately without waiting for 09:00:

```bash
launchctl kickstart -k gui/$(id -u)/com.example.token-budget-daily
ls -lt ~/Reports/token-budget/ | head -3
```

## Adapt this section

- Edit `Label` in the plist to your reverse-DNS namespace (e.g.
  `tld.you.token-budget-daily`). The filename must match.
- Edit the time in `<key>StartCalendarInterval</key>`.
- Edit `bin/run-daily-report.sh` to point at *your* tracker
  (`token-budget-tracker`'s `report.py`, or your equivalent).
- Run `./bin/install.sh` once. Re-run after editing the plist.
- Confirm with `launchctl print gui/$(id -u)/<Label> | head -30`.

## Verifying it works

```bash
# Status
launchctl print gui/$(id -u)/com.example.token-budget-daily | grep -E "state|last exit"

# Trigger once
launchctl kickstart -k gui/$(id -u)/com.example.token-budget-daily

# Read the stderr log
tail -f ~/Library/Logs/token-budget-daily.err.log
```
