# llm-output-python-requests-no-timeout-detector

Single-pass python3 stdlib scanner for HTTP client calls in
LLM-emitted Python that omit a `timeout=` argument. Covers
`requests`, `httpx`, `urllib3`, and conventionally-named bound
session/client method calls.

## Why it exists

The Python `requests` library defaults to **no timeout**. A
`requests.get(url)` against an attacker-controlled host that
accepts the TCP connection but never replies will block your
worker forever, exhausting the connection pool and silently
DoSing your service. Same trap exists in `urllib3.PoolManager`,
and `httpx`'s module-level convenience calls are smelly even
though `httpx` defaults to a 5-second timeout — visible config
beats invisible defaults.

LLMs reliably forget the `timeout=` kwarg because the simplest
form on the public internet is `requests.get(url)`. This detector
forces the caller to be explicit:

```python
requests.get(url, timeout=5)            # safe
requests.get(url)                        # blocks forever
```

## What it flags

- `requests.get | post | put | patch | delete | head | options |
  request(...)` without `timeout=`.
- `httpx.get | post | put | patch | delete | head | options |
  request(...)` without `timeout=`.
- `urllib3.PoolManager().request(...)` /
  `HTTPSConnectionPool(...).urlopen(...)` without `timeout=`.
- Bound session/client calls on the conventional variable names
  `session`, `sess`, `s`, `client`, `http`, `api`, `cli`:
  `session.get(...)`, `client.post(...)`, etc.

## What it does NOT flag

- Any call with `timeout=` set to **any** value (including
  `None` — that's an explicit and reviewable choice).
- `requests.Session()` / `httpx.Client(timeout=...)` constructor
  calls — those are configuration, not the HTTP call itself.
- Method calls on variables outside the recognized vocabulary —
  too noisy. If your codebase uses `gh.get(...)` or
  `slack.post(...)`, extend `SESSION_NAMES` in `detect.py`.
- Lines marked with the trailing suppression marker
  `# no-timeout-ok`.
- Occurrences inside `#` comments or string literals (the scanner
  masks both before matching).

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

Targets `*.py` files plus any file whose first line is a python shebang.

## Worked example

`examples/bad/` contains 11 dangerous shapes; `examples/good/`
contains 8 safe shapes plus the suppression marker. `verify.sh`
asserts `bad >= 11` and `good == 0`.

```
$ ./verify.sh
bad findings:  11 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/bad_cases.py:8:5: requests-get-no-timeout — r = requests.get("https://example.com")
examples/bad/bad_cases.py:11:5: requests-post-no-timeout — r = requests.post("https://example.com", json={"a": 1})
examples/bad/bad_cases.py:14:5: requests-put-no-timeout — r = requests.put("https://example.com", data=b"x")
examples/bad/bad_cases.py:17:5: requests-delete-no-timeout — r = requests.delete("https://example.com")
examples/bad/bad_cases.py:20:5: requests-request-no-timeout — r = requests.request("GET", "https://example.com")
examples/bad/bad_cases.py:23:5: httpx-get-no-timeout — r = httpx.get("https://example.com")
examples/bad/bad_cases.py:26:5: httpx-post-no-timeout — r = httpx.post("https://example.com", json={"a": 1})
examples/bad/bad_cases.py:29:16: urllib3-request-no-timeout — http = urllib3.PoolManager().request("GET", "https://example.com")
examples/bad/bad_cases.py:33:5: session-get-no-timeout — r = session.get("https://example.com")
examples/bad/bad_cases.py:36:5: session-post-no-timeout — r = session.post("https://example.com", data=b"y")
examples/bad/bad_cases.py:40:5: session-get-no-timeout — r = client.get("https://example.com")
# 11 finding(s)
```

## Suppression

Add `# no-timeout-ok` at the end of any line you have audited.
Common legitimate cases: a long-poll endpoint, an SSE stream, or
a `client.get(...)` where the client was constructed with a
visible `timeout=` default.

## Layout

```
llm-output-python-requests-no-timeout-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/bad_cases.py
    └── good/good_cases.py
```

## Limitations

- Single-line analysis. A `requests.get(` whose call spans many
  lines isn't reassembled — extend with a parenthesis-aware
  multi-line buffer if your codebase formats long calls.
- The session-name vocabulary is fixed. Add to `SESSION_NAMES`
  in `detect.py` to extend.
- No flow analysis. A `Session` configured with a default
  timeout via an adapter or a `functools.partial` won't be
  recognized; the linter still wants a visible `timeout=` at
  the call site. Use `# no-timeout-ok` for the audited cases.
- `timeout=None` passes the lint. That's intentional: the
  reviewer should see the explicit opt-in to infinite blocking
  in the diff.
- No cross-file analysis.
