# llm-output-csharp-xxe-xmlreader-detector

Pure-stdlib python3 line scanner that flags XML reader / serializer
construction in LLM-emitted C# where the resulting parser is left in
its default DTD-permissive state. The detector reports a finding only
when an at-risk constructor / factory is called **and** the same file
never opts in to any of the well-known XXE mitigations.

## Why

The .NET XML stack has historically defaulted to processing DOCTYPEs
and resolving external entities, with several behaviour changes across
runtime versions. A snippet as small as

```csharp
var doc = new XmlDocument();
doc.Load(userSuppliedStream);
```

…is exploitable for classic XXE on legacy frameworks: local-file
disclosure via `file://` external entities, SSRF via `http://attacker/`,
billion-laughs DoS via nested entity expansion, and out-of-band
exfiltration via parameter entities. The same hazard applies to
`XmlTextReader`, `XmlReader.Create` (when `XmlReaderSettings.DtdProcessing`
is not set), `XPathDocument`, `XmlSerializer.Deserialize` (when fed an
unguarded reader), and `DataSet` / `DataTable` `ReadXml` paths.

Vendor and OWASP XXE-cheat-sheet guidance prescribes
either `DtdProcessing.Prohibit`, `DtdProcessing.Ignore`, or an explicit
`XmlResolver = null`. LLMs frequently emit the construction line and
the `Load()` line and skip the mitigation block entirely.

CWE references:

- **CWE-611**: Improper Restriction of XML External Entity Reference (XXE).
- **CWE-776**: Improper Restriction of Recursive Entity References (billion laughs).
- **CWE-918**: Server-Side Request Forgery (when XXE is used to fetch URLs).

## Usage

```sh
python3 detect.py path/to/Foo.cs
python3 detect.py path/to/src/   # recurses *.cs
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

A line in a `.cs` file that constructs an at-risk XML reader:

- `new XmlDocument(...)`
- `new XmlTextReader(...)`
- `new XPathDocument(...)`
- `new XmlSerializer(...)`
- `new DataSet(...)` / `new DataTable(...)`
- `XmlReader.Create(...)` / `XmlDictionaryReader.Create(...)`
- `XmlDocument.Load(...)` / `XPathDocument.Load(...)` / `XDocument.Load(...)` / `XElement.Load(...)`

…**only when** the same file contains none of the recognised
mitigations.

## What it does NOT flag

- Files that configure any mitigation anywhere — for example any of
  these tokens occurring in the file silences every finding in that
  file:
  - `DtdProcessing.Prohibit` or `DtdProcessing.Ignore`
  - `XmlResolver = null`
  - `ProhibitDtd = true` (legacy `XmlReaderSettings`)
  - `MaxCharactersFromEntities = ...`
  - `XmlSecureResolver` (constructed anywhere)
- Construction inside string literals (regular `"..."` and verbatim
  `@"..."`) or after `//` line comments — handled by a C#-aware line
  stripper.
- Lines suffixed with `// xxe-ok`.

This is intentionally coarse: a single mitigation token anywhere in
the file silences findings, on the basis that the worst LLM mistake is
omitting mitigation entirely. Pair with a stricter SAST tool if you
need per-reader proof.

## Worked example

```sh
cd templates/llm-output-csharp-xxe-xmlreader-detector
./verify.sh
```

`verify.sh` runs the detector against `examples/bad/` (multiple
positive cases — `XmlDocument.Load`, `XmlReader.Create`, `XPathDocument`,
`XmlSerializer.Deserialize`, `DataSet.ReadXml`, plus a `new XmlTextReader`
case) and `examples/good/` (each at-risk constructor is paired with the
matching mitigation, plus a suppressed line and a verbatim-string false
positive). It asserts:

- detector exits non-zero on `bad/` with at least the expected number
  of findings,
- detector exits zero on `good/` with zero findings,
- prints `PASS` if both hold.
