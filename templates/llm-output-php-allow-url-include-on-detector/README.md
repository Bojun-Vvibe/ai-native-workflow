# llm-output-php-allow-url-include-on-detector

Static lint that flags PHP runtime configurations enabling
`allow_url_include`.

PHP's `allow_url_include = On` lets `include` / `require` /
`include_once` / `require_once` accept URL wrappers (`http://`,
`https://`, `ftp://`, `data://`, `php://`, ...) as the path
argument. With even a single tainted include target this becomes a
one-shot Remote File Inclusion (RFI) primitive that fetches and
executes attacker-controlled PHP from a remote origin (CWE-98 /
CWE-94). PHP itself ships with this disabled for a reason — turning
it on is almost never the right answer, and LLM-generated configs
often flip it without comment.

LLM-generated `php.ini`, `.user.ini`, `.htaccess`, Dockerfile `RUN`
lines, and bootstrap PHP files routinely paste in shapes like:

```ini
allow_url_fopen = On
allow_url_include = On
```

```php
ini_set('allow_url_include', '1');
require $_GET['module'] . '.php';
```

This detector flags those shapes. `allow_url_fopen` is *not* flagged
on its own (it has legitimate uses for `file_get_contents`); only
`allow_url_include` is treated as the RFI smoking gun.

## What it catches

- INI: `allow_url_include = On|1|true|yes`.
- PHP: `ini_set('allow_url_include', '1')` and friends.
- `.htaccess`: `php_flag allow_url_include on` /
  `php_value allow_url_include 1`.
- Dockerfile `RUN` lines that `sed` / `echo` `allow_url_include` to
  a truthy value into `php.ini`.

## CWE references

- [CWE-98](https://cwe.mitre.org/data/definitions/98.html):
  Improper Control of Filename for Include/Require Statement in PHP
  Program ('PHP Remote File Inclusion')
- [CWE-94](https://cwe.mitre.org/data/definitions/94.html):
  Improper Control of Generation of Code ('Code Injection')
- [CWE-829](https://cwe.mitre.org/data/definitions/829.html):
  Inclusion of Functionality from Untrusted Control Sphere

## False-positive surface

- `allow_url_include = Off` / `0` / `false` is treated as safe.
- Any file containing `# php-allow-url-include-allowed` is skipped
  wholesale (use for legacy compatibility fixtures).
- Lines starting with `#` or `//` are treated as comments.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at
  least one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
