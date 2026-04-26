# llm-output-trailing-whitespace-in-code-fence-detector

## Failure mode

LLM output frequently contains trailing spaces or tabs on lines **inside**
fenced code blocks (```` ``` ```` or `~~~`). These are invisible when the
markdown is rendered, so reviewers miss them, but they:

- break `pre-commit` / `editorconfig` / lint hooks downstream,
- silently corrupt shell commands written with backslash continuation
  (`\<space><newline>` does **not** join the next line — it ends the command),
- pollute diffs when humans later edit the file,
- break heredoc / YAML payloads embedded in fenced examples.

The detector only flags trailing whitespace **inside fences**. Trailing
whitespace in normal prose is left to other tools (markdown often uses
two trailing spaces as a hard line break, which is intentional).

## How it works

- Pure python3 stdlib, no deps.
- Scans line by line, tracking whether the cursor is inside a ` ``` ` or `~~~`
  fence.
- For every line inside a fence (excluding the closing fence line itself),
  compares `line` to `line.rstrip(' \t')`. Any difference is a finding.
- Reports line number, fence start line, what kind of trailing whitespace
  (spaces vs tabs), and a 60-char preview of the line content.

## Exit codes

- `0` — clean, no trailing whitespace inside any fenced code block.
- `1` — at least one finding; details printed to stdout.

## Invocation

```
python3 detector.py path/to/output.md
# or
cat path/to/output.md | python3 detector.py
```

## Worked example (actual output)

Run on `example/good-input.md`:

```
clean: no trailing whitespace inside fenced code blocks
EXIT=0
```

Run on `example/bad-input.md`:

```
FOUND 4 trailing-whitespace finding(s) inside fenced code blocks:
  line 6 (fence opened at line 5): 3 space(s) trailing | preview: 'echo hello'
  line 7 (fence opened at line 5): 3 space(s) trailing | preview: 'ls -la \\'
  line 14 (fence opened at line 13): 1 tab(s) trailing | preview: 'def f():'
  line 15 (fence opened at line 13): 2 space(s) trailing | preview: '    return 1'
EXIT=1
```

Note line 7: `ls -la \` followed by 3 trailing spaces — exactly the case where
shell continuation silently breaks for a copy-pasting user.
