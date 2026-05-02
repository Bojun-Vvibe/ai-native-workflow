# llm-output-haproxy-stats-no-auth-detector

Flags HAProxy configurations that expose the **stats interface
without authentication**, enable `stats admin if TRUE` anonymously,
or open the runtime `stats socket` with world-writable Unix
permissions (`mode 666`+).

## Why this matters

The HAProxy stats page leaks rich operational data: backend names,
server health, request rates, sticky-table contents, queue depths.
With `stats admin if TRUE` and no auth, anonymous callers can also
**enable / disable backends** at will. Internet-scanned daily.

Maps to:

- **CWE-306** Missing Authentication for Critical Function
- **CWE-732** Incorrect Permission Assignment for Critical Resource
- **OWASP A05:2021** Security Misconfiguration

## Why LLMs ship this

Quickstart blogs paste the minimal demo block:

```
listen stats
    bind *:8404
    stats enable
    stats uri /
```

into "production" configs without ever adding `stats auth`.

## Heuristic

Per `listen` / `frontend` / `backend` block: if the block contains
`stats enable` or `stats uri ...` but no `stats auth user:pass` (and
no `stats http-request auth`), flag it. Also flags
`stats admin if TRUE` without auth, and `stats socket ... mode <NNN>`
where the last digit ≥ 6 (world-writable).

## Usage

```
python3 detect.py path/to/haproxy.cfg
python3 detect.py /etc/haproxy/   # walks dir
```

Exit codes: 0 = clean, 1 = findings, 2 = usage error.

## Smoke (verified)

```
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Sample finding:

```
examples/bad/01-listen-stats-no-auth.cfg:12: HAProxy block `listen stats`
  exposes stats page (enable) without `stats auth user:pass` ->
  anonymous access to backend topology / health (CWE-306)
examples/bad/04-stats-socket-world-writable.cfg:2: HAProxy
  `stats socket ... mode 666` is world-writable -> any local user
  can drive the runtime API (CWE-732)
```

## Layout

```
detect.py                # stdlib-only, walks dirs
smoke.sh                 # end-to-end harness
examples/bad/*.cfg       # 4 misconfigured configs
examples/good/*.cfg      # 3 properly authenticated configs
```
