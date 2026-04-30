# llm-output-java-xxe-saxparser-detector

Pure-stdlib python3 line scanner that flags XML parser construction in
LLM-emitted Java where the resulting parser is left in its insecure JDK
default — DOCTYPEs allowed, external general / parameter entities
resolved, external DTDs / stylesheets fetched. The detector reports a
finding only when the file constructs an at-risk parser **and** never
configures any of the well-known XXE mitigations.

## Why

The Java XML stack ships insecure-by-default. A snippet as small as

```java
SAXParserFactory f = SAXParserFactory.newInstance();
SAXParser p = f.newSAXParser();
p.parse(input, handler);
```

…is exploitable for classic XXE — local file disclosure via
`file://` external entities, SSRF via `http://attacker/`, billion-laughs
DoS via nested entity expansion, and out-of-band exfiltration via
parameter entities. The same hazard applies to
`DocumentBuilderFactory`, `XMLInputFactory` (StAX),
`TransformerFactory`, `SchemaFactory`, JDOM `SAXBuilder`, and dom4j
`SAXReader`.

OWASP's XXE cheat sheet documents the exact `setFeature` / `setProperty`
calls that close each hole. LLMs frequently emit the construction line
and the `parse()` line and skip the mitigation block entirely.

CWE references:

- **CWE-611**: Improper Restriction of XML External Entity Reference (XXE).
- **CWE-776**: Improper Restriction of Recursive Entity References (billion laughs).
- **CWE-918**: Server-Side Request Forgery (when XXE is used to fetch URLs).

## Usage

```sh
python3 detect.py path/to/Foo.java
python3 detect.py path/to/src/   # recurses *.java
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

A line in a `.java` file that constructs an at-risk XML parser:

- `SAXParserFactory.newInstance(...)`
- `DocumentBuilderFactory.newInstance(...)`
- `XMLInputFactory.newInstance(...)`
- `TransformerFactory.newInstance(...)` / `SAXTransformerFactory.newInstance(...)`
- `SchemaFactory.newInstance(...)`
- `XMLReaderFactory.newInstance(...)`
- `new SAXBuilder(...)` (JDOM)
- `new SAXReader(...)` (dom4j)

…**only when** the same file contains none of the recognised
mitigations.

## What it does NOT flag

- Files that configure any mitigation anywhere — for example any of
  these tokens occurring in the file silences every finding in that
  file:
  - The Apache feature URI `disallow-doctype-decl`
  - `external-general-entities` / `external-parameter-entities`
  - `load-external-dtd`
  - `setExpandEntityReferences(false)` / `setXIncludeAware(false)`
  - `XMLConstants.FEATURE_SECURE_PROCESSING`
  - `XMLConstants.ACCESS_EXTERNAL_DTD` / `ACCESS_EXTERNAL_SCHEMA` / `ACCESS_EXTERNAL_STYLESHEET`
  - `XMLInputFactory.SUPPORT_DTD` / `isSupportingExternalEntities` /
    `javax.xml.stream.isSupportingExternalEntities`
- Construction inside string literals or after `//` line comments
  (handled by a Java-aware line stripper).
- Lines suffixed with `// xxe-ok`.

This is intentionally coarse: a single mitigation token anywhere in the
file silences findings, on the basis that the worst LLM mistake is
omitting mitigation entirely. Pair with a stricter SAST tool if you
need per-parser proof.

## Worked example

```sh
cd templates/llm-output-java-xxe-saxparser-detector
./verify.sh
```

`verify.sh` runs the detector against `examples/bad/` (multiple
positive cases — different factory classes, plus a JDOM and a dom4j
case) and `examples/good/` (each parser is paired with the matching
mitigation, plus one suppressed line and one literal-string false
positive). It asserts:

- detector exits non-zero on `bad/` with at least the expected number
  of findings,
- detector exits zero on `good/` with zero findings,
- prints `PASS` if both hold.
