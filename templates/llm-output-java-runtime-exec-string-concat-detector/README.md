# llm-output-java-runtime-exec-string-concat-detector

Pure-stdlib python3 line scanner that flags `Runtime.getRuntime().exec(...)`
and `new ProcessBuilder(...)` invocations in LLM-emitted Java where the
command argument is a non-literal string — built via `+` concatenation,
`String.format`, `String.formatted`, `MessageFormat.format`, or a bare
variable reference.

## Why

`Runtime.exec(String)` and the single-string `ProcessBuilder(String...)`
constructor tokenise the command on whitespace using `StringTokenizer`,
but they do **not** invoke a shell — yet LLMs frequently emit
`Runtime.getRuntime().exec("sh -c " + userInput)` to "make pipes work".
That detour through `sh -c` re-introduces full shell interpretation of
metacharacters, and the raw concatenation form (without `sh -c`) is
still vulnerable to argument injection because every space in
`userInput` becomes a token boundary.

CWE references:

- **CWE-78**: OS Command Injection.
- **CWE-77**: Improper Neutralization of Special Elements used in a Command.
- **CWE-88**: Argument Injection.

## Usage

```sh
python3 detect.py path/to/Foo.java
python3 detect.py path/to/src/   # recurses *.java
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

- `Runtime.getRuntime().exec(<expr>)` where `<expr>` is non-literal:
  contains `+`, `String.format(`, `.formatted(`, `MessageFormat.format(`,
  or is a bare identifier / method-call reference.
- `new ProcessBuilder(<expr>)` with the same condition.
- `Runtime.getRuntime().exec(new String[]{ ..., <expr>, ... })` where
  any element of the array literal is non-literal.

## What it does NOT flag

- `Runtime.getRuntime().exec("ls -la /tmp")` — fully literal command.
- `new ProcessBuilder("git", "status")` — argv form, all literals.
- `new ProcessBuilder(List.of("git", "status"))` — argv form.
- Lines suffixed with `// runtime-exec-ok` (audited construction with
  per-token sanitisation).

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every `examples/bad/*.java` case and is
silent on every `examples/good/*.java` case.
