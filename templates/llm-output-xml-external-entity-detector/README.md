# llm-output-xml-external-entity-detector

Defensive lint detector that flags Python XML parsing surfaces
vulnerable to **XML External Entity (XXE)** attacks — including
billion-laughs / "external entity expansion" / DTD-fetch / SSRF
pivots — when an LLM-generated snippet uses the stdlib XML
namespace or `lxml.etree` without hardening.

## Why this exists

When asked "parse this XML in Python", an LLM almost always
emits one of:

```python
import xml.etree.ElementTree as ET
tree = ET.parse(user_path)            # XXE-vulnerable in older runtimes
```

```python
import lxml.etree
root = lxml.etree.fromstring(blob)    # DTD + entity expansion enabled
```

The hardened path is **`defusedxml`** (drop-in for stdlib /
lxml) or an explicit `lxml.etree.XMLParser(resolve_entities=
False, no_network=True, dtd_validation=False)`. This detector
audits a tree of `*.py` files and flags every unhardened parse
call so reviewers can swap the import.

## What is flagged

| Surface                                                  | Kind                                |
|----------------------------------------------------------|-------------------------------------|
| `xml.etree.ElementTree.parse` / `.fromstring` / `.iterparse` / `.XML` / `.XMLParser` | `xxe-stdlib-xml-parse`              |
| `xml.dom.minidom.parse` / `.parseString`                 | `xxe-stdlib-xml-parse`              |
| `xml.dom.pulldom.parse` / `.parseString`                 | `xxe-stdlib-xml-parse`              |
| `xml.sax.parse` / `.parseString` / `.make_parser`        | `xxe-stdlib-xml-parse`              |
| `xml.parsers.expat.ParserCreate`                         | `xxe-stdlib-xml-parse`              |
| `ET.parse(...)`, `etree.parse(...)`, `minidom.parse(...)` etc. via the conventional aliases — unless the alias is bound from `defusedxml` | `xxe-alias-<method>`                |
| `lxml.etree.parse` / `.fromstring` / `.XML` / `.iterparse` without an `XMLParser(resolve_entities=False, ...)` visible in the file | `xxe-lxml-<method>-no-hardening`    |

## What is NOT flagged

* Anything in the `defusedxml.*` namespace.
* Aliases bound from `defusedxml` (e.g. `import
  defusedxml.ElementTree as ET` then `ET.parse(...)`).
* `lxml.etree.parse(...)` calls in a file that constructs a
  hardened `XMLParser(resolve_entities=False, ...)`.
* Lines marked with a trailing `# xxe-ok` comment.
* Occurrences inside `#` comments or string literals.

## Usage

```sh
python3 detect.py path/to/code [more/paths ...]
```

Exit code `1` if any findings, `0` otherwise. python3 stdlib
only — no external deps.

## Sample output

```
examples/bad/parse.py:9:12: xxe-alias-parse — return ET.parse(path)
examples/bad/parse.py:13:12: xxe-alias-fromstring — return ET.fromstring(blob)
examples/bad/parse.py:21:12: xxe-alias-parse — return minidom.parse(path)
examples/bad/parse.py:33:12: xxe-stdlib-xml-parse — return xml.sax.parse(path, handler)
examples/bad/parse.py:41:12: xxe-lxml-parse-no-hardening — return lxml.etree.parse(path)
# 13 finding(s)
```

## Worked example

```sh
bash verify.sh
# bad findings:  13 (rc=1)
# good findings: 0 (rc=0)
# PASS
```

## Suppression

Append `# xxe-ok` to a line that has been audited as safe (e.g.
fully internal trusted-only call). Reviewers should require an
adjacent comment justifying every suppression.

## Limitations

* Regex-based — does not perform full AST resolution. Will miss
  XML calls hidden behind dynamic attribute lookup
  (`getattr(ET, "parse")(...)`) or aliased through
  intermediate variables (`p = ET.parse; p(path)`).
* Only inspects `*.py` files (and `python` shebang scripts).
* `lxml` hardening is detected at file scope — a hardened
  parser declared anywhere in the file silences `lxml.etree.*`
  flags throughout it. Tighten with a per-call review when the
  file mixes safe and unsafe lxml usage.
