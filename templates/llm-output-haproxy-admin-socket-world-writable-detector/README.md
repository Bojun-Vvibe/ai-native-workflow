# llm-output-haproxy-admin-socket-world-writable-detector

## Purpose

Flags HAProxy `global` configs that expose the runtime/stats socket with
`level admin` in a way that lets unintended callers issue state-changing
commands (`disable server`, `set server ... agent`, `add map`, `del map`,
`set ssl cert`, `clear table`, ...).

The pattern an LLM most often emits — when asked "let me drain backends from
a script" — is one of:

- a TCP socket bound to `*:9999` or `0.0.0.0:9999` with `level admin`;
- a unix socket with `mode 666` so the script user can write to it;
- a unix socket with `level admin` and **no** `mode` and **no**
  `user`/`group` clause, leaving permissions to whatever umask the haproxy
  process happened to have.

Any of these gives a local (or in case 1, remote) caller full administrative
control of the proxy.

## Signals (any one is sufficient to flag)

1. `stats socket ipv4@... level admin` (or `ipv6@`, `*:`, `0.0.0.0:`,
   `[::]:`) — TCP admin socket on a public-shape address.
2. `stats socket /path ... mode 666|777` — unix socket with world-writable
   permissions.
3. `stats socket /path ... level admin` with no `mode 0xxx` clause and no
   `user`/`group`/`uid`/`gid` clause on the same line.
4. `stats socket ipv4@... expose-fd listeners` — the master-worker
   reload-over-network pattern, dangerous unless ACL'd.

## How the detector works

`detector.sh` is pure `grep -nE` plus one small loop for the
"admin-without-mode-or-user" combination check. It emits one
`FLAG <signal-id> <file>:<lineno> <text>` per finding and always exits 0.

It does not parse the full HAProxy grammar; it only inspects single
`stats socket` lines, which is where this misconfiguration always lives.

## False-positive notes

- A `stats socket` line wrapped across multiple physical lines via
  backslash-continuations will only have its first physical line scanned;
  the haproxy parser does not allow continuations in `global` directives,
  so this is not a real-world FP source.
- `level operator` and `level user` sockets are intentionally not flagged —
  those grant read-only and stats-only access respectively.
- Loopback TCP sockets (`127.0.0.1:`, `[::1]:`) are not flagged.

## Fixtures

- `fixtures/bad/`: 4 files — TCP wildcard admin, unix mode 666, unix
  bare-admin (no mode/user), and TCP `expose-fd listeners`.
- `fixtures/good/`: 4 files — mode 600 + user/group, operator-level only,
  loopback TCP at `level user`, and a config with no admin socket at all.

## Smoke

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```
