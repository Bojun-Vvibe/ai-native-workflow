# llm-output-csharp-binaryformatter-deserialize-detector

Stdlib-only Python detector that flags C# source calling
`.Deserialize(...)` on any of the historically-dangerous binary
formatters:

- `BinaryFormatter`
- `NetDataContractSerializer`
- `SoapFormatter`
- `LosFormatter`
- `ObjectStateFormatter`

These formatters embed CLR type names in the payload and instantiate
those types during `Deserialize`. On attacker-controlled input that
yields a working RCE chain (see ysoserial.net). The .NET team has
marked `BinaryFormatter` obsolete and is removing it from the
platform; this detector catches LLM-emitted code that still uses it.

This maps to **CWE-502: Deserialization of Untrusted Data**.

## Heuristic

Two passes, both regex-based, stdlib only.

**Pass 1 — direct call.** Find any dangerous type name; within the
same statement (up to the next `;`), look for `.Deserialize(`. Catches
the inline form:

```csharp
return new BinaryFormatter().Deserialize(stream);
```

**Pass 2 — variable tracking.** Find `var x = new
<DangerousType>(...)` (or the explicitly-typed equivalent) and then
any `x.Deserialize(` later in the file. Catches the common split form:

```csharp
var f = new BinaryFormatter();
// ... 20 lines of unrelated code ...
return f.Deserialize(stream);
```

Comments (`//` and `/* ... */`) are blanked out before scanning so
mentions in docs do not produce findings, while line numbers stay
correct.

## What we accept (no false positive)

- `JsonSerializer.Deserialize<T>(...)` — `System.Text.Json`.
- `XmlSerializer.Deserialize(...)` — different threat model, out of scope.
- `JsonConvert.DeserializeObject<T>(...)` — Newtonsoft, out of scope.
- Calling `.Serialize(...)` (write-side) on a dangerous formatter.
- The dangerous type name appearing only inside `//` or `/* */`
  comments.
- Class names that merely *contain* a dangerous substring, e.g.
  `MyBinaryFormatterHelper2` — we match on word boundaries.

## What we flag

- `new BinaryFormatter().Deserialize(stream)` (inline)
- `var f = new BinaryFormatter(); ... f.Deserialize(stream)` (split)
- `SoapFormatter`, `LosFormatter`, `NetDataContractSerializer`,
  `ObjectStateFormatter` analogs of the above
- Field-initializer style:
  `private ObjectStateFormatter osf = new ObjectStateFormatter();`
  followed by `osf.Deserialize(...)`

## Limits / known false negatives

- Cross-file flow: if the formatter is constructed in one file and the
  variable is passed into another, we do not follow it.
- Reflection: `Activator.CreateInstance(typeof(BinaryFormatter))`
  followed by `MethodInfo.Invoke("Deserialize", ...)` slips past us.
- `dynamic` typing where the variable's static type is `dynamic`
  obscures the formatter type from the regex.

## Usage

```bash
python3 detect.py path/to/File.cs
python3 detect.py path/to/dir/   # walks *.cs and *.cshtml
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_binary_formatter_var.cs    # var f = new BinaryFormatter(); f.Deserialize(...)
  02_inline_new.cs              # new BinaryFormatter().Deserialize(...)
  03_soap_formatter.cs          # SoapFormatter
  04_netdatacontract.cs         # NetDataContractSerializer
  05_los_formatter.cs           # LosFormatter
  06_object_state_formatter.cs  # field-init + later .Deserialize
examples/good/
  01_system_text_json.cs        # JsonSerializer.Deserialize
  02_xml_serializer.cs          # XmlSerializer.Deserialize
  03_only_in_comments.cs        # type name only in comments
  04_newtonsoft_json.cs         # JsonConvert.DeserializeObject
  05_serialize_only.cs          # .Serialize(...) write-side
  06_namesake_class.cs          # MyBinaryFormatterHelper2 (no boundary match)
```
