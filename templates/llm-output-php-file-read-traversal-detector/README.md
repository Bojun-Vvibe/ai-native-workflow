# llm-output-php-file-read-traversal-detector

Static detector for **CWE-22 (Path Traversal)** and **CWE-73
(External Control of Filename)** in PHP code that an LLM produces
when it just wants the file read to "work". The classic shapes:

```php
$body = file_get_contents($_GET['path']);
$body = file_get_contents("/var/data/" . $_POST['name']);
readfile($_REQUEST['file']);
$h    = fopen($_GET['f'], 'r');
$lines = file($_GET['log']);
```

All five accept `../../../etc/passwd` (or `/etc/passwd` directly)
without complaint. Worse, single-arg `file_get_contents` is also
SSRF-loaded because PHP's stream wrappers transparently fetch
`http://`, `ftp://`, `php://`, `data://`, and `phar://` URLs from
the very same call — so the same line is simultaneously a CWE-918
SSRF foot-gun.

The safe shape resolves through `realpath` and verifies the result
sits inside an explicit base directory before opening:

```php
$base = realpath('/srv/data');
$real = realpath($base . '/' . basename($name));
if ($real === false || strncmp($real, $base . '/', strlen($base) + 1) !== 0) {
    http_response_code(400);
    exit;
}
$body = file_get_contents($real);
```

## What this flags

Four kinds:

1. **php-file-get-contents-tainted** — `file_get_contents(<expr>)`
   where `<expr>` references a PHP superglobal (`$_GET`, `$_POST`,
   `$_REQUEST`, `$_COOKIE`, `$_FILES`, `$_SERVER`, `$_ENV`) or
   contains string concatenation with one, or wraps a known input
   helper (`filter_input`, `getenv`, `apache_request_headers`,
   `stream_get_contents`).
2. **php-readfile-tainted** — same condition for `readfile(<expr>)`.
3. **php-fopen-tainted** — same condition for `fopen(<expr>, ...)`
   (only the path argument is examined).
4. **php-file-tainted** — same condition for `file(<expr>)`
   (line-array reader).

The detector is anchored on the global function name (negative
look-behind for `>`, `:`, `\`, identifier chars), so user-defined
methods named `file_get_contents` on a class do **not** trigger.

## What this does NOT flag

- Fully literal paths:
  `file_get_contents('/etc/hostname')`,
  `readfile(__DIR__ . '/static/banner.txt')`.
- Inline `realpath(...)`-wrapped arguments
  (`file_get_contents(realpath($x))`) — treated as audited.
- Method calls on user objects (`$loader->file_get_contents(...)`).
- Lines suffixed with `// llm-allow:php-path-traversal` or
  `# llm-allow:php-path-traversal`.
- References to the call shape inside `//`, `#`, or string literals
  — comments and string contents are scrubbed before matching.

In Markdown, only fenced ` ```php ` / ` ```phtml ` blocks are
scanned; prose mentions of `file_get_contents` are ignored.

## Usage

```bash
python3 detect.py path/to/file.php
python3 detect.py src/                # recursive
```

Stdlib only (no third-party deps). Exit code:

- `0` — no findings
- `1` — at least one finding (each printed as
  `path:line: kind: <source line>`)
- `2` — usage error

## Suppression

Append `// llm-allow:php-path-traversal` (or `# llm-allow:...`) to
the offending line after auditing it. The marker is matched
literally and skips the entire line.

## Worked example

```bash
./verify.sh
# bad findings:  8 (rc=1)
# good findings: 0 (rc=0)
# PASS
```

`examples/bad/handler.php` carries 8 distinct vulnerable shapes
(one per line). `examples/good/handler.php` covers literal paths,
`realpath`-anchored reads, user-class methods named the same as
the global functions, and the suppression marker — all of which
must stay clean.

## File types scanned

`.php`, `.phtml`, `.inc`, `.md`, `.markdown`. In Markdown, only
` ```php ` / ` ```phtml ` fenced blocks are considered.

## Related detectors

- `llm-output-php-include-user-input-detector` — `include` /
  `require` of user input (CWE-98 RFI, distinct sink set).
- `llm-output-php-unserialize-detector` — `unserialize` of
  attacker-controlled input (CWE-502).
- `llm-output-ruby-open-uri-ssrf-detector` — same family of
  "single call does fetch + file read + pipe" foot-gun in Ruby.
