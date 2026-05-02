# llm-output-php-display-errors-on-detector

Static lint that flags PHP runtime configurations shipping with
`display_errors` turned on.

PHP's `display_errors = On` causes warnings, notices, and full stack
traces — including absolute file paths, DB hostnames, and sometimes
serialized object dumps — to be emitted directly into the HTTP
response body. In production this is both a sensitive-information
disclosure (CWE-209 / CWE-215) and a recon enabler that fingerprints
framework versions, file layouts, and env vars for downstream attacks.

LLM-generated `php.ini`, `.user.ini`, `.htaccess`, Dockerfile `RUN`
lines, and bootstrap `index.php` files routinely paste in shapes like:

```ini
display_errors = On
display_startup_errors = 1
error_reporting = E_ALL
```

```php
ini_set('display_errors', '1');
error_reporting(E_ALL);
```

This detector flags those shapes while accepting:

- `display_errors = stderr` (logged, not rendered to client)
- `display_errors = Off` / `0` / `false`
- files containing `# php-display-errors-allowed` for committed dev
  fixtures.

## What it catches

- INI: `display_errors = On|1|true|yes|stdout`.
- PHP: `ini_set('display_errors', '1')` and friends.
- `.htaccess`: `php_flag display_errors on` /
  `php_value display_errors 1`.
- Dockerfile `RUN` lines that `sed` / `echo` `display_errors=On` into
  `php.ini`.

## CWE references

- [CWE-209](https://cwe.mitre.org/data/definitions/209.html):
  Generation of Error Message Containing Sensitive Information
- [CWE-215](https://cwe.mitre.org/data/definitions/215.html):
  Insertion of Sensitive Information Into Debugging Code
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html):
  Exposure of Sensitive Information to an Unauthorized Actor

## False-positive surface

- `display_errors = stderr` is treated as safe (errors go to the log
  pipe, not the response body).
- Any file containing the comment `# php-display-errors-allowed` is
  skipped wholesale.
- Lines starting with `#` or `//` are treated as comments and ignored.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
