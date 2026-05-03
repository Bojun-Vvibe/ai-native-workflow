# llm-output-varnish-vcl-purge-no-acl-detector

## What it catches

LLM-generated Varnish VCL files that handle `PURGE` or `BAN` requests
without gating them by an ACL of trusted client IPs. Three concrete
failure modes:

1. **No `acl` block at all** — `vcl_recv` invokes `return (purge)` or
   `ban(...)` immediately on `req.method == "PURGE"`, so any client
   can wipe the cache.
2. **ACL defined but never referenced** — the snippet declares
   `acl purge_allowed { ... }` but `vcl_recv` never does
   `if (!client.ip ~ purge_allowed) { return (synth(405)); }`. The ACL
   is dead code.
3. **World-open ACL entry** — the ACL exists and is checked, but it
   contains `"0.0.0.0"/0` or `"any"`, which defeats the point.

## Why an LLM produces this

Models routinely emit short "PURGE handler" snippets focused on the
happy path. The ACL gate is one extra `if` block that is easy to omit,
and `acl` blocks placed earlier in the file *look* like they're doing
something even when nothing references them.

## Approach

Stdlib regex. Strips `# ...`, `// ...`, and `/* ... */` comments first
so commented hints (`# forgot: client.ip ~ purge_allowed`) don't
accidentally satisfy the ACL-check probe. Then:

- finds `acl <name> { ... }` blocks
- looks for `return (purge)` or `ban(...)` in non-comment code
- looks for any `client.ip ~ <name>` reference
- scans each ACL body for world-open entries

## Usage

```sh
python3 detector.py path/to/default.vcl [more.vcl ...]
```

Exit code = number of flagged files (capped at 255). No external deps.

## Layout

```
detector.py
bad/         # 4 misconfigured fixtures
good/        # 3 properly-gated fixtures
worked-example.md
```
