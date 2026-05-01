# llm-output-java-log-injection-crlf-detector

Static detector for **CWE-117 (Improper Output Neutralisation for
Logs)** — aka **log forging / log injection / log splitting** — in
Java (and Kotlin) code that LLMs emit when they want a log line to
"include the user's value":

```java
log.info("user logged in: " + username);
LOGGER.warn("query=" + req.getParameter("q"));
LOGGER.error(String.format("failed for %s", input));
log.info(input + " requested resource");
```

If the spliced value contains a CR or LF, the attacker can forge an
entire fake log line (`\nINFO admin authenticated`) that downstream
log analytics treat as authentic. If the log sink renders HTML
(Kibana, an in-house dashboard), splicing in `<script>` becomes a
stored XSS in the log viewer (CWE-79 in the secondary surface).

The safe shape strips CR/LF (and ideally other control chars) before
logging and uses the parameterised form:

```java
String safe = username.replaceAll("[\\r\\n\\t]", "_");
log.info("user logged in: {}", safe);
```

> **Note.** Parameterised logging *alone* is **not** automatically
> safe against log forging — the SLF4J formatter still embeds `\n`
> from the placeholder verbatim. But it is the established Java
> convention, and most teams pair it with a CRLF-stripping encoder
> at the sink. This detector therefore treats parameterised calls
> with no concatenation as out of scope, and only flags the
> string-concatenation / pre-rendered-format / bare-tainted shapes
> that are unambiguously dangerous.

## What this flags

Three kinds, all anchored on a recognised logger receiver
(`log`, `logger`, `LOG`, `LOGGER`, `slf4jLogger`, or any identifier
ending in `Logger`) followed by a level method (`trace`, `debug`,
`info`, `warn`, `warning`, `error`, `fatal`, `severe`):

1. **java-log-injection-concat** — argument list contains a `+`
   outside string literals (string concatenation in the call).
2. **java-log-injection-format** — first argument is a
   `String.format(...)` / `"...".formatted(...)` /
   `MessageFormat.format(...)` call. The formatter has already
   produced the final string, so any sink-side placeholder
   handling that would normally CRLF-escape is bypassed.
3. **java-log-injection-bare-tainted** — single-argument call where
   the argument is a bare identifier matching one of `input`,
   `userInput`, `username`, `user`, `req`, `request`, `param`,
   `params`, `payload`, `body`, `data`, `value`, `raw`,
   `queryString`, `remoteUser`, **or** any identifier ending in
   `Param`, `Header`, `Cookie`, or `Input`.

## What this does NOT flag

- Parameterised logging with a literal template and no `+`:
  `log.info("user={}", user)` — see note above; out of scope.
- All-literal calls: `log.info("starting up")`.
- Calls on non-logger receivers (e.g. `out.println(x + y)` is a
  different problem; the receiver heuristic is intentionally narrow
  to keep precision high).
- `++` / `+=` (not concat at top level).
- Lines suffixed with `// llm-allow:log-injection`.

In Markdown, only fenced ` ```java ` / ` ```kotlin ` / ` ```kt `
blocks are scanned.

## Usage

```bash
python3 detect.py path/to/Foo.java
python3 detect.py src/main/java/                 # recursive
```

Stdlib only (no third-party deps). Exit code:

- `0` — no findings
- `1` — at least one finding (each printed as
  `path:line: kind: <source line>`)
- `2` — usage error

## Suppression

Append `// llm-allow:log-injection` to the offending line after
auditing it. The marker is matched literally and skips the entire
line.

## Worked example

```bash
./verify.sh
# bad findings:  9 (rc=1)
# good findings: 0 (rc=0)
# PASS
```

`examples/bad/BadHandler.java` carries 9 distinct vulnerable shapes
(concat at INFO/WARN/prefix, `String.format`, `MessageFormat.format`,
`.formatted`, bare `*Param` / `*Header` / `userInput`).
`examples/good/GoodHandler.java` covers literal templates,
parameterised calls with sanitised values, allow-listed bare names
(`message`), `++`/`+=` non-concat, and the suppression marker.

## File types scanned

`.java`, `.kt`, `.md`, `.markdown`. In Markdown, only
` ```java ` / ` ```kotlin ` / ` ```kt ` fenced blocks are
considered.

## Related detectors

- `llm-output-java-runtime-exec-string-concat-detector` — CWE-78
  command injection via `Runtime.exec` / `ProcessBuilder` with
  string concatenation (sibling pattern, different sink).
- `llm-output-java-spel-injection-detector` — CWE-917 expression
  injection (different sink, same concat-trigger family).
