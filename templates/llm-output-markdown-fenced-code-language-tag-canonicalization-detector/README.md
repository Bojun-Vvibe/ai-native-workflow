# llm-output-markdown-fenced-code-language-tag-canonicalization-detector

Detects fenced code blocks whose info-string language tag is a known *alias*
of a canonical name (e.g. `py` instead of `python`, `sh` instead of `bash`,
`yml` instead of `yaml`, `js` instead of `javascript`).

## Why this matters

LLMs trained on mixed-source Markdown happily emit the same language under
several aliases inside one document. Static-site generators, syntax
highlighters, and code-search tools key off the literal tag string, so a
mix of `py` / `python` / `python3` produces:

* inconsistent syntax highlighting between adjacent blocks
* missing highlights when the renderer's alias map differs from the author's
* false negatives in `grep -A 'lang:python'` style code-block extraction

Canonicalizing the tag is a cheap, high-signal lint that catches a class
of drift no human reviewer notices until the rendered page looks wrong.

## What it detects

Each opening fence whose first info-string token matches a known alias is
flagged with the canonical replacement. Currently mapped aliases:

| alias                                  | canonical     |
| -------------------------------------- | ------------- |
| `py`, `py3`, `python3`                 | `python`      |
| `js`, `node`                           | `javascript`  |
| `ts`                                   | `typescript`  |
| `sh`, `shell`, `zsh`                   | `bash`        |
| `yml`                                  | `yaml`        |
| `rb`                                   | `ruby`        |
| `kt`                                   | `kotlin`      |
| `rs`                                   | `rust`        |
| `golang`                               | `go`          |
| `c++`, `cxx`                           | `cpp`         |
| `objc`                                 | `objective-c` |
| `cs`, `c#`                             | `csharp`      |
| `ps`, `ps1`                            | `powershell`  |
| `md`                                   | `markdown`    |
| `dockerfile`                           | `docker`      |
| `html5`, `htm`                         | `html`        |

Edit `ALIASES` in `detect.py` to fit your project's house style.

## What it ignores

* Fences with no info string (handled by the missing-tag detector)
* Fences whose tag is unknown to the alias table (handled by the spelling
  detector)
* Tildes / backticks inside other fenced blocks (single-pass nesting)

## How to run

```bash
python3 detect.py example/bad.md
```

Exit codes:

* `0` — clean
* `1` — one or more findings printed to stdout
* `2` — usage / IO error

## CI usage

```yaml
- name: Lint markdown code-fence languages
  run: |
    find docs -name '*.md' -print0 | \
      xargs -0 -n1 python3 templates/llm-output-markdown-fenced-code-language-tag-canonicalization-detector/detect.py
```

The script exits non-zero on findings, so it composes naturally with
`set -e` shell pipelines and any CI that fails the step on non-zero exit.

## Worked example

`example/bad.md` mixes five aliased tags with one canonical and one
unknown tag. Running the detector produces `example/expected-output.txt`
verbatim and exits with status `1`.
