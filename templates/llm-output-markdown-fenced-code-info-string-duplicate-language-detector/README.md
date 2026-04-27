# llm-output-markdown-fenced-code-info-string-duplicate-language-detector

Flags fenced code block opening lines whose info string repeats a
language token, including alias forms (`py` after `python`,
`sh`/`bash` after `shell`, etc.) and decorator forms
(`language=python`).

## What it detects

LLMs frequently emit fences that name the language twice, often
when stitching examples from multiple sources:

```
```python python          <-- exact duplicate
```python py              <-- alias duplicate (py == python)
```javascript language=javascript   <-- decorator duplicate
```sh bash shell          <-- triple alias collision
```bash (sh)              <-- bracketed alias
```

Most renderers either silently keep the first token (so the extra
text becomes invisible noise) or display the entire info string
above the block as raw text. Either way the output is sloppy and
breaks any downstream tool that parses info strings (mdformat,
syntax-highlight selectors, AST consumers).

The detector handles common alias groups out of the box:

| canonical | aliases                          |
| --------- | -------------------------------- |
| python    | py, python3                      |
| javascript| js, node                         |
| typescript| ts                               |
| bash      | sh, shell, zsh                   |
| yaml      | yml                              |
| markdown  | md                               |
| cpp       | c++, cxx                         |
| csharp    | c#, cs                           |
| ruby      | rb                               |
| rust      | rs                               |
| go        | golang                           |
| text      | plain, plaintext, txt            |
| html      | htm                              |

It is **fence-aware**: it only inspects opening fence lines and
correctly skips fence-looking content inside outer fences (the
4-backtick wrapping pattern used to demo markdown inside markdown
is preserved).

## Why it matters for LLM-generated markdown

- Hidden noise: most renderers discard the second token, so the
  author cannot tell the model emitted garbage.
- Tooling fragility: `mdformat`, `prettier --parser=markdown`, and
  AST-based linters parse the full info string; some hard-fail on
  unrecognized tokens.
- Diff churn: reformatters strip the extra token, producing noisy
  diffs on otherwise content-only PRs.

## Usage

```
python3 detect.py path/to/file.md
```

## Exit codes

| code | meaning              |
| ---- | -------------------- |
| 0    | no findings          |
| 1    | findings on stdout   |
| 2    | usage / read error   |

Output format:
`<file>:<line>: duplicate language token(s) in info string: [<canonical>...]: <raw line>`

## Worked example

Run against `examples/bad.md`:

```
$ python3 detect.py examples/bad.md
examples/bad.md:5: duplicate language token(s) in info string: ['py']: ```python python
examples/bad.md:11: duplicate language token(s) in info string: ['py']: ```python py
examples/bad.md:17: duplicate language token(s) in info string: ['javascript']: ```javascript language=javascript
examples/bad.md:23: duplicate language token(s) in info string: ['bash']: ```bash (sh)
examples/bad.md:29: duplicate language token(s) in info string: ['bash']: ```sh bash shell
$ echo $?
1
```

Run against `examples/good.md`:

```
$ python3 detect.py examples/good.md
$ echo $?
0
```

The bad file produces 5 findings covering exact, alias, decorator,
bracketed, and triple-alias duplications. The good file confirms
that single-token info strings, attribute-style info strings
(`title="..."`), and an outer 4-backtick fence wrapping demo content
that *contains* a duplicate are all correctly accepted.
