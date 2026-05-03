# llm-output-tikv-security-empty-ca-path-detector

## What it catches

LLM-generated TiKV config snippets (`tikv.toml`) that *look* like they
configure TLS but actually leave the cluster in plaintext / half-broken
mTLS. Three failure modes:

1. **Empty TLS keys** — `ca-path = ""`, `cert-path = ""`, `key-path = ""`.
   Operators paste the snippet, restart TiKV, and TiKV accepts plaintext
   client and peer connections because empty strings are treated as
   "not configured."
2. **Empty `[security]` block** — section header is present (signaling
   intent) but no path keys are defined. Same plaintext outcome.
3. **Half-config** — `ca-path` is set but `cert-path` or `key-path` is
   missing/empty, which TiKV refuses *or* silently downgrades depending
   on version. Either way it's a misconfiguration that doesn't survive
   first contact with production.

## Why an LLM produces this

Models often emit a `[security]` block as a "best practice" placeholder
and leave the values for the human to fill in. The result looks
plausible but ships unprotected.

## Scope (out)

- A TiKV config with **no** `[security]` block at all is *not* flagged.
  That's a separate concern (plaintext-by-default), and conflating the
  two would generate noise on dev/test snippets.

## Usage

```sh
python3 detector.py path/to/tikv.toml [more.toml ...]
```

Exit code = number of files flagged (capped at 255). Stdlib only.

## Layout

```
detector.py           # the checker (stdlib regex, ~80 lines)
bad/                  # 4 misconfigured fixtures
good/                 # 3 properly-configured fixtures
worked-example.md     # verbatim run output
```

See `worked-example.md` for the captured run.
