# llm-output-pomerium-insecure-server-true-detector

Detects Pomerium identity-aware proxy configurations where the data plane
runs in cleartext mode via `insecure_server: true` (or, equivalently, the
`POMERIUM_INSECURE_SERVER=true` environment variable in compose / env
files). In this mode Pomerium serves HTTP — not HTTPS — on its public
listener.

## What it flags

- A YAML key `insecure_server` whose value is the literal `true`,
  `True`, `TRUE`, `yes`, `on`, or `"true"`.
- An env-style line `POMERIUM_INSECURE_SERVER=true` (case-insensitive
  on the value, optionally quoted, optionally exported).
- The same key inside a `docker compose` `environment:` block, whether
  written as a YAML map (`POMERIUM_INSECURE_SERVER: "true"`) or list
  (`- POMERIUM_INSECURE_SERVER=true`).

Comment-only lines (everything after `#` on the line) are ignored, and
explicit `false` values are not flagged.

## Why it's bad

Pomerium is meant to terminate TLS for the apps it fronts and to use
mTLS / signed JWTs to forward identity to upstreams. With
`insecure_server: true` the front door speaks plain HTTP, which means:

- Browser cookies (including the Pomerium session cookie) traverse the
  network in cleartext — anyone on path can hijack a logged-in session.
- The OIDC redirect that carries the authorization `code` is observable
  on the wire.
- Browsers refuse to set `Secure` cookies, so even cookies marked
  `Secure` upstream are silently downgraded.
- Pomerium's own authenticate / authorize endpoints lose integrity:
  responses can be tampered with by an on-path attacker.

The flag exists for a few narrow scenarios — local development, or a
deployment where Pomerium is behind a TLS-terminating sibling proxy on
the same loopback interface. Those uses should be reviewed explicitly
rather than left in production configs.

## References

- Pomerium reference, `insecure_server`
  <https://www.pomerium.com/docs/reference/insecure-server>
- Pomerium production deployment guide — TLS section
- OWASP ASVS V9.1 — TLS for all authenticated traffic

## Usage

```
./detect.sh path/to/config.yaml
cat config.yaml | ./detect.sh -
```

Exit codes:

- `0` — no issue found
- `1` — at least one insecure_server=true setting found (printed with
  `path:lineno:` prefix)
- `2` — usage / IO error

## Limitations

The detector is line-oriented; it does not parse YAML. It is therefore
robust against the full set of YAML quirks (anchors, multi-doc files)
but will not follow `!include` directives or environment substitution.
A value that resolves to `true` only after substitution (e.g.
`insecure_server: ${INSECURE}`) is not flagged here — pair it with the
env-file scan if you template configs.
