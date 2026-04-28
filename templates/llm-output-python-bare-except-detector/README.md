# llm-output-python-bare-except-detector

## Problem

LLMs frequently emit Python code with bare `except:` clauses, which catch
every exception including `KeyboardInterrupt` and `SystemExit`. This is a
well-known anti-pattern (PEP 8, `pycodestyle E722`, Bandit `B001`):

* Hides real bugs by swallowing programmer errors (`NameError`, `TypeError`).
* Makes Ctrl-C and orderly process shutdown unreliable.
* Often combined with `pass`, producing silently-broken code.

This detector flags:

1. `except:` with no exception class.
2. `except BaseException:` (catching the universal base — usually wrong).
3. `except Exception:` *immediately followed by `pass`* on the next non-blank
   line (silent swallow).

It is **code-fence aware**: when given Markdown, it scans only fenced code
blocks tagged `python`, `py`, or `python3`. When given a `.py` file, it scans
everything.

It does **not** import or execute the target file — pure regex/line scan,
stdlib only.

## Usage

```
python3 detector.py path/to/file.py
python3 detector.py path/to/notes.md
cat snippet.py | python3 detector.py -
```

Always exits `0`.

## Finding format

```
<path>:<line>: <code>: <message> | <trimmed offending line>
```

Codes:

- `PYEXC001` — bare `except:`
- `PYEXC002` — `except BaseException:`
- `PYEXC003` — `except Exception:` followed by `pass` (silent swallow)

Trailing `# findings: <N>` summary.

## Example

```
$ python3 detector.py examples/bad.py
examples/bad.py:3: PYEXC001: bare except clause | except:
examples/bad.py:9: PYEXC002: except BaseException catches KeyboardInterrupt/SystemExit | except BaseException:
examples/bad.py:15: PYEXC003: except Exception followed by silent pass | except Exception:
# findings: 3

$ python3 detector.py examples/good.py
# findings: 0
```
