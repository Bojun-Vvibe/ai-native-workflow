# llm-output-markdown-task-list-checkbox-syntax-validator

A small, dependency-free linter that flags malformed GitHub-Flavored Markdown
task list items in LLM output.

LLMs frequently produce checklists that *look* like GFM task lists but render
as plain bullets because of subtle whitespace or mark errors. Examples:

| Bad                | Why                                          |
|--------------------|----------------------------------------------|
| `- []`             | empty brackets                               |
| `-[ ] item`        | no space between bullet and `[`              |
| `- [ ]item`        | no space between `]` and content             |
| `- [y] item`       | non-standard mark (only ` `, `x`, `X` valid) |
| `- [  ] item`      | two spaces inside brackets                   |
| `- [ x ] item`     | padded mark                                  |

When fed back into PR review or release-checklist tooling, these silently
collapse into ordinary bullets — the "checked" state is lost.

## Usage

```sh
python3 validator.py path/to/file.md      # exit 1 on any defect
cat file.md | python3 validator.py -      # stdin mode
```

## Worked example

Input: [`example/sample.md`](example/sample.md) — a release plan with a mix of
valid and malformed items.

Run:

```sh
$ python3 validator.py example/sample.md
```

Actual stdout (exit code `1`):

```
line 6: missing space between bullet '-' and '['
  > -[ ] Notify on-call (missing space between bullet and bracket)
line 7: empty brackets '[]' (need ' ', 'x', or 'X')
  > - [] Draft changelog (empty brackets)
line 8: missing space after ']' (got 'R')
  > - [ ]Run smoke suite (missing space after closing bracket)
line 9: invalid checkbox mark 'y' (only ' ', 'x', 'X' allowed)
  > - [y] Approval recorded (invalid mark)
line 10: invalid checkbox mark '  ' (only ' ', 'x', 'X' allowed)
  > - [  ] Backup snapshot taken (two spaces inside)
line 14: invalid checkbox mark ' x ' (only ' ', 'x', 'X' allowed)
  > * [ x ] Close incident channel (padded mark)

FAIL: 6 malformed task list item(s)
```

Two well-formed items (`- [ ] Verify CI green`, `- [x] Tag candidate commit`)
plus the trailing numbered list at the bottom are correctly *not* flagged.

## When to wire this in

- Pre-commit hook on any directory that stores LLM-drafted release plans,
  retros, or PR templates.
- CI step on docs PRs that regenerate checklists from a model.
- Inline self-check inside an agent loop right before posting a checklist back
  to the user.

## Limits

- Only inspects single-line task list items. Multi-line item bodies are not
  parsed.
- Does not detect *missing* checkboxes (e.g. plain bullets that should have
  been task items) — that needs intent, not syntax.
- Does not validate nesting indentation; pair with a list-marker indentation
  linter if needed.
