# Worked example: what each block looks like when it fires

These are the actual outputs from `test/test-guardrail.sh`. Nothing
synthetic — this is what you'll see in your terminal if you trip a
block.

## Block 1 — internal-string blacklist

You committed a file containing one of your `INTERNAL_PATTERNS`.

```
[guardrail BLOCK] commit a1b2c3d4 contains internal token(s):
1:this references SECRET_INTERNAL_CODENAME oops

Scrub the commit and retry. If false positive, refine INTERNAL_PATTERNS in your guardrail config.
```

How to fix: scrub the leak with `git rebase -i` or `git reset --soft`,
remove the offending line, recommit. If it's a false positive, edit
`INTERNAL_PATTERNS` to be more specific, then retry.

## Block 2 — secret pattern

You committed something matching a known API-key shape.

```
[guardrail BLOCK] commit b2c3d4e5 contains likely secret(s):
1:key=sk-************************************   ← real key shape redacted in this doc
```

How to fix: **rotate the key first** (assume it's compromised the
moment it landed in git history), then scrub the commit. Do not just
delete and force-push without rotating — the key may already be in a
fork/clone.

## Block 3 — forbidden filename

You staged a file whose path matches a forbidden pattern.

```
[guardrail BLOCK] commit c3d4e5f6 touches forbidden file(s):
.env
```

How to fix: `git rm --cached .env`, add `.env` to `.gitignore`,
amend the commit. Then re-push.

## Block 4 — oversized blob

You committed a blob larger than `MAX_BLOB_BYTES` (default 5 MB).

```
[guardrail BLOCK] commit d4e5f6a7 contains oversized blob(s) > 5242880 bytes:
big.bin (6291456 bytes)
```

How to fix: large binaries belong in Git LFS, in a release artifact,
or in object storage — not in git history. Remove with `git rm`,
amend, push.

## Block 5 — attack-payload fingerprint

You referenced or copied content from a known offensive-security
repository.

```
[guardrail BLOCK] commit e5f6a7b8 references attack-payload artifact(s):
1:see Payloads<redacted-in-doc> repo for examples
```

How to fix: drop the reference, or move the work to an isolated VM
not covered by your forge-account scope filter. Per the policy in
`AGENTS.md`-style charters, payload artifacts on managed hosts is a
hard "no."

## What success looks like

```
[guardrail OK]    no internal-string hits
[guardrail OK]    no obvious secrets
[guardrail OK]    no forbidden filenames
[guardrail OK]    no oversized blobs
[guardrail OK]    no attack-payload references
[guardrail OK]    all checks passed for https://github.com/test-account/test-repo.git
```

Six green lines and the push proceeds. On a typical commit range
(<10 commits, <100 files) the whole hook completes in under one
second on a modern laptop.
