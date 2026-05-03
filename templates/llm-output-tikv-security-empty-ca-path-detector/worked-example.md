# Worked example

Run against the bundled fixtures. Output captured verbatim from
`python3 detector.py` on macOS, CPython 3.13.

## bad/ — expect 4/4 flagged

```
$ python3 detector.py bad/*.toml
bad/01-empty-ca-path.toml: FLAGGED
  - [security].ca-path declared but empty (TLS disabled)
  - [security].cert-path declared but empty (TLS disabled)
  - [security].key-path declared but empty (TLS disabled)
bad/02-security-block-no-keys.toml: FLAGGED
  - [security] block present but no ca-path/cert-path/key-path set
bad/03-half-config-missing-cert.toml: FLAGGED
  - [security].ca-path set but cert-path missing/empty (mTLS broken)
  - [security].ca-path set but key-path missing/empty (mTLS broken)
bad/04-half-config-empty-key.toml: FLAGGED
  - [security].key-path declared but empty (TLS disabled)
  - [security].ca-path set but key-path missing/empty (mTLS broken)
summary: 4/4 flagged
```

## good/ — expect 0/3 flagged

```
$ python3 detector.py good/*.toml
good/01-full-mtls.toml: ok
good/02-no-security-block.toml: ok
good/03-mtls-with-comment.toml: ok
summary: 0/3 flagged
```

## Interpretation

- All four bad fixtures were caught with specific, actionable messages.
- The "no `[security]` block at all" good fixture is intentionally not
  flagged (see README → Scope).
- The mTLS-with-inline-comments fixture confirms the regex tolerates
  trailing `# ...` comments on key lines.
