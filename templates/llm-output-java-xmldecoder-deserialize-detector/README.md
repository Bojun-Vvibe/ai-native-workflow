# llm-output-java-xmldecoder-deserialize-detector

Stdlib-only Python detector for **Java `java.beans.XMLDecoder`**
deserialization sinks (CWE-502). Catches every shape of
`new XMLDecoder(...).readObject()` an LLM might emit when asked to
"load a Java bean from XML".

## Problem statement

`java.beans.XMLDecoder` is a Turing-complete deserializer. Its XML
grammar (`<object class="..."><void method="..."/>...`) lets the
input choose **any** class on the classpath and invoke **any** public
method on it. The canonical PoC is a four-line XML document that
calls `Runtime.getRuntime().exec(...)`. There is no allow-list mode,
no `resolveClass` hook, no safe configuration: `XMLDecoder` over
untrusted input is unconditional RCE.

```java
XMLDecoder dec = new XMLDecoder(req.getInputStream());
return dec.readObject();   // attacker-chosen class + method
```

## CWE references

- [CWE-502](https://cwe.mitre.org/data/definitions/502.html)
  Deserialization of Untrusted Data
- [CWE-20](https://cwe.mitre.org/data/definitions/20.html)
  Improper Input Validation

## What the detector flags

A `*.java` file is flagged if, after stripping comments and string
literals, it contains BOTH:

1. `new XMLDecoder(...)` — or the fully qualified
   `new java.beans.XMLDecoder(...)` form, and
2. `.readObject(` anywhere in the same file.

The two-condition rule keeps the rule precise: a file that imports
`XMLDecoder` for type-only purposes (or only ever encodes via
`XMLEncoder`) stays quiet.

## What it deliberately does NOT flag

- Files that import or reference `XMLDecoder` only inside comments.
- `XMLEncoder` (the safe symmetric serializer).
- `ObjectInputStream.readInt()` and other primitive-only reads.
- DOM/SAX/StAX parsing (different sink, covered by separate XXE
  detectors).

## Usage

```bash
python3 detect.py path/to/File.java
python3 detect.py src/main/java/        # recurses *.java
./smoke.sh                              # bundled examples
```

Exit codes:

- `0` — no findings
- `1` — at least one finding (paths printed to stdout)
- `2` — usage error

## Layout

```
detect.py
smoke.sh
examples/bad/      # 6 files, each MUST trigger
examples/good/     # 6 files, each MUST stay quiet
```
