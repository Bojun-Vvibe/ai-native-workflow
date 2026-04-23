# <owner>/<repo> — YYYY-MM-DD

> <The one-line `why` from targets.json — why you track this repo.>

**Window:** YYYY-MM-DDTHH:MM:SSZ → YYYY-MM-DDTHH:MM:SSZ
**Default branch:** `<branch>`
**Source:** [github.com/<owner>/<repo>](https://github.com/<owner>/<repo>)

## Daily summary

> _LLM-generated. May contain errors — click through before acting._

<1–3 paragraphs. Cover, in priority order:

1. The **single most important thing** that happened in this repo
   today. If there was a release, it's almost always the release.
   If there was a refactor sweep, name the theme and the bottom-up
   reading order.
2. The **second-most-important** thing, if it's worth surfacing.
3. **Skip-this** items: bot commits, formatter passes, dep-bumps,
   regenerated artifacts. Name them so the reader knows you saw
   them and decided they're noise.

End with a "Bottom line:" sentence — what should the reader actually
do today based on this repo's activity? "Skip" is a valid answer.>

## Releases

<List or "_None in window._">

- [**vX.Y.Z**](https://github.com/<owner>/<repo>/releases/tag/vX.Y.Z) — <release title> — <date>
  - <one-line summary of what's in it, if non-trivial>

## Merged PRs

<List or "_None in window._". Group by author or by theme if >10.>

- [#NNNN](https://github.com/<owner>/<repo>/pull/NNNN) — <title> — _@<author>_

## Open PRs (new or updated)

<List or "_None in window._". For high-volume repos, just link the
filtered view: `?q=is:pr+is:open+updated:>YYYY-MM-DD`>

- [#NNNN](https://github.com/<owner>/<repo>/pull/NNNN) — <title> — _@<author>_ — <state: opened | reviewed | etc>

## Notable Issues

<List or "_None in window._". Filter aggressively: only issues with
substantive activity (>1 comment in window, label change, or close).
Bot-only activity does not count.>

- [#NNNN](https://github.com/<owner>/<repo>/issues/NNNN) — <title> — _@<author>_

## Commits on `<default-branch>`

<List or "_None in window._". Cap at ~20 — if more, link the filtered
view and list only the merge commits + tagged releases.>

- [`<short-sha>`](https://github.com/<owner>/<repo>/commit/<sha>) <subject> — _@<author>_
