# Worked example

Verbatim output from `python3 detector.py` against the bundled
fixtures. CPython 3.13 on macOS, no third-party deps.

## bad/ — expect 4/4 flagged

```
$ python3 detector.py bad/*.vcl
bad/01-no-acl-block.vcl: FLAGGED
  - VCL handles PURGE/BAN but defines no `acl` block — anyone can purge cache
bad/02-acl-not-checked.vcl: FLAGGED
  - VCL defines acl block(s) [purge_allowed] but never checks client.ip against them
bad/03-world-open-acl.vcl: FLAGGED
  - acl `purge` contains a world-open entry (0.0.0.0/0 or "any")
bad/04-ban-no-acl.vcl: FLAGGED
  - VCL handles PURGE/BAN but defines no `acl` block — anyone can purge cache
summary: 4/4 flagged
```

## good/ — expect 0/3 flagged

```
$ python3 detector.py good/*.vcl
good/01-purge-gated.vcl: ok
good/02-no-purge-handling.vcl: ok
good/03-ban-gated.vcl: ok
summary: 0/3 flagged
```

## Interpretation

- `bad/02` is the interesting case: the file *contains* the string
  `client.ip ~ purge_allowed`, but only inside a `# forgot: ...`
  comment. The detector strips comments before checking, so it
  correctly reports the ACL as never enforced.
- `good/02` (no PURGE/BAN handler at all) is intentionally not flagged
  — that's a different shape of cache config and out of scope here.
- `good/03` exercises `ban(...)` gated by an ACL, confirming the
  detector covers BAN as well as PURGE.
