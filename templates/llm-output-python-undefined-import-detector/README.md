# llm-output-python-undefined-import-detector

## Problem

LLMs frequently emit Python code with imports that look plausible but
correspond to no installed package — a hallucinated dependency. Examples
seen in the wild:

* `import openai_helper` (no such package)
* `import pandas_utils` (sounds real, isn't)
* `from langchain_tools import Agent` (typo / made-up sub-module)

These imports pass syntax checks and only blow up at runtime, often deep
inside an agent loop where the failure is hard to attribute back to the
generation step.

This detector parses Python source with `ast` and flags top-level imports
whose root module is **neither** in the Python standard library **nor** in
an explicit allowlist of known third-party packages.

It is **code-fence aware**: when given Markdown, it scans only fenced code
blocks tagged `python`, `py`, or `python3`. When given a `.py` file, it
scans everything.

It does **not** import or execute the target code — pure `ast.parse`,
stdlib only.

## Usage

```
python3 detector.py path/to/file.py
python3 detector.py --known requests --known numpy snippet.py
python3 detector.py --known-file requirements.txt notes.md
cat snippet.py | python3 detector.py --known fastapi -
```

Always exits `0`.

## Finding format

```
<path>:<line>: <code>: <message> | <offending statement>
```

Codes:

* `PYIMP000` — block could not be parsed (syntax error inside fenced code)
* `PYIMP001` — `import X` where `X` is not stdlib and not in the known set
* `PYIMP002` — `from X import …` where `X` is not stdlib and not in the known set

Trailing `# findings: <N>` summary.

Relative imports (`from . import …`) are ignored — they cannot be resolved
without package context.

## Example

```
$ python3 detector.py examples/bad.py
examples/bad.py:1: PYIMP001: import of unknown module 'pandas_utils' ...
examples/bad.py:2: PYIMP002: from-import of unknown module 'openai_helper' ...
examples/bad.py:3: PYIMP001: import of unknown module 'fastapi_extra' ...
# findings: 3

$ python3 detector.py --known requests --known json_logger examples/good.py
# findings: 0
```

## Limitations

* The known-set is a static allowlist — the detector cannot reach into a
  virtualenv. Pair it with a `requirements.txt` via `--known-file` for the
  best signal.
* Conditional imports inside `try/except ImportError` blocks are still
  flagged; treat those findings as informational.
* The stdlib list is frozen at a CPython 3.8–3.13 superset and may lag
  newly-added modules.
