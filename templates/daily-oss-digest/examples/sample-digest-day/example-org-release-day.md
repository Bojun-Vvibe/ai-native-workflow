# example-org/release-day — 2026-04-23

> Streaming-rewrite landed today; we depend on the streaming API.

**Window:** 2026-04-22T23:59:59.000Z → 2026-04-23T23:59:59.000Z
**Default branch:** `main`
**Source:** [github.com/example-org/release-day](https://github.com/example-org/release-day)

## Daily summary

> _LLM-generated. May contain errors — click through before acting._

**v2.4.0 shipped.** The release closes out the streaming-rewrite
epic that's been in flight since v2.2: the public streaming API now
returns an `AsyncIterator<StreamChunk>` instead of an event-emitter,
and the chunk shape stabilized to a tagged-union (`{kind: "text",
text: string} | {kind: "tool_call", call: ToolCall} | {kind: "done",
usage: Usage}`). This is a **breaking change** for any consumer of
the streaming surface; the migration guide is linked from the
release notes.

The 8 merged PRs today are all release-prep: changelog, version
bump, two final test fixes, and three doc updates. The 14 commits
include the v2.4.0 tag commit and 4 `release-bot` artifacts (safe
to skip).

If you depend on this in a downstream, the v2.4.0 release notes are
the only thing you need to read today; everything else is
context-zero.

**Bottom line:** read the v2.4.0 release notes; if you consume the
streaming API, the migration guide.

## Releases

- [**v2.4.0**](https://github.com/example-org/release-day/releases/tag/v2.4.0) — Streaming rewrite — 2026-04-23
  - Breaking: `stream()` now returns `AsyncIterator<StreamChunk>`.
  - Breaking: chunk shape is a tagged union (see notes).
  - Migration guide linked from the notes.

## Merged PRs

- [#882](https://github.com/example-org/release-day/pull/882) — chore: bump to v2.4.0 — _@example-maintainer_
- [#881](https://github.com/example-org/release-day/pull/881) — docs: streaming migration guide — _@example-maintainer_
- [#880](https://github.com/example-org/release-day/pull/880) — test: pin AsyncIterator semantics — _@example-author-2_
- [...5 more]

## Open PRs (new or updated)

- [#883](https://github.com/example-org/release-day/pull/883) — bug: streaming retries fire twice on transient network error — _@example-user-4_

## Notable Issues

_None in window._

## Commits on `main`

_14 commits today, including 4 `release-bot` artifact commits._
Notable non-bot commits:

- [`f0a1b2c`](https://github.com/example-org/release-day/commit/f0a1b2c) chore(release): v2.4.0 — _@example-maintainer_
- [`c7d8e9a`](https://github.com/example-org/release-day/commit/c7d8e9a) docs: streaming migration guide (#881) — _@example-maintainer_
- [...]
