---
pr_number: 0000
pr_title: "<exact PR title>"
repo: <owner>/<name>
author: <github-handle>
url: https://github.com/<owner>/<name>/pull/0000
fetched_at: YYYY-MM-DD
files_changed: 0
additions: 0
deletions: 0
focus_files:
  - path/to/file/that/contains/the/substantive/change.ext
  - path/to/its/test/file.ext
note: "<one-line: which subset of the diff this review focuses on, if not all. Especially useful when the PR includes rebase noise or unrelated reformatting that you are deliberately not reviewing.>"
---

# Context

<2–4 paragraphs. Cover, in order:

1. What subsystem of the project this PR lives in. One paragraph.
2. The constraint, invariant, or external contract the PR is
   navigating (e.g., "Anthropic API requires byte-stable thinking
   blocks", "the parser must preserve column offsets", "this struct
   is serialized to disk and any field rename is a wire break").
3. Why this matters more than the LOC count suggests. If the LOC
   count overstates importance, say so here too.>

# Diff walkthrough

<Hunk by hunk on the **substantive** files only. For each substantive
hunk:

- Name what the hunk does in one sentence.
- Quote the smallest diff that makes the point — usually 5–15 lines.
- Explain why the change is correct (or, if you find a bug, why it
  is not).

Skip mechanical hunks (formatting, import reordering, dep bumps) with
a single line: "Hunks 4–7 are mechanical reformatting; not reviewed
in detail.">

# Test coverage

<What do the new/changed tests actually verify? Be specific:

- "T1 covers the happy path with a single empty `redacted_thinking`
  block — exercises the new predicate but not the cache-hint hunk."
- "T2 is a regression for the bug from #12345 — it would have caught
  the original symptom."

Then: what would they NOT catch? Are there integration-level
behaviors the unit tests don't reach? Does the gap matter, or is it
covered elsewhere?>

# Risks

<Numbered list. Each risk is a concrete failure mode of "if this
lands as-is, then under condition X, Y will go wrong." Avoid generic
risks ("could have unintended side effects"); name the specific path.

1. <risk one — concrete, with the conditions that would trigger it>
2. <risk two — ditto>
3. ...>

# Clarifying questions for the author

<Numbered list. Each question is specific and answerable. Avoid
rhetorical questions or sermons disguised as questions.

1. <question one>
2. <question two>
3. ...>

# Verdict

**<Ready to merge | Ready to merge after Q&A | Changes requested |
Not ready>**: <one paragraph. State the verdict, the conditions
attached to it, and what the author would need to do (if anything)
to move it to "ready to merge".>

# What I learned

<One paragraph. The durable, generalizable lesson — the thing you'd
remember about this PR a year from now even if you forgot which repo
it was in. Examples of good shapes:

- "The pattern here is that wire formats are load-bearing in places
  that look like noise. Any normalization layer between an agent and
  an LLM provider needs an explicit 'do not touch' predicate for
  opaque payloads, and the predicate should be expressed positively
  ('preserve when X') rather than negatively ('filter unless Y')."

- "When two semantic categories share a key, splitting their
  handling code is worth it even if the bodies are identical, so
  future maintainers have a stable place to attach divergent logic."

If you can't write this paragraph, you didn't understand the PR
deeply enough — go back and read more of the surrounding code.>
