# llm-output-php-expose-php-on-detector

Static lint that flags PHP configurations shipping with
`expose_php = On`.

When `expose_php` is enabled, PHP advertises its presence and exact
version in the `X-Powered-By` HTTP response header
(e.g. `X-Powered-By: PHP/8.1.4`). That hands an attacker a free
fingerprint they can map directly against the published CVE list to
pick a working exploit. The PHP manual recommends
`expose_php = Off` for production. LLM-generated `php.ini` snippets,
Dockerfiles, and ansible `lineinfile` fragments often leave the
upstream default `On` in place — or worse, paste a dev example that
flips it back on:

```ini
expose_php = On
```

```dockerfile
RUN echo "expose_php = On" >> /usr/local/etc/php/php.ini
```

This detector flags those shapes while accepting:

- `expose_php = Off` / `off` / `0` / `false` / `no`
- files containing `; php-expose-php-allowed` or
  `# php-expose-php-allowed` for committed dev fixtures
- comment lines (`;` or `#` prefix)

## What it catches

- `php.ini`: `expose_php = On|1|true|yes` at any scope.
- Dockerfile `RUN` lines that `sed` / `echo` `expose_php = On` (or
  any truthy form) into a `php.ini`-style file.

## CWE references

- [CWE-200](https://cwe.mitre.org/data/definitions/200.html):
  Exposure of Sensitive Information to an Unauthorized Actor
- [CWE-209](https://cwe.mitre.org/data/definitions/209.html):
  Generation of Error Message Containing Sensitive Information
- [CWE-497](https://cwe.mitre.org/data/definitions/497.html):
  Exposure of Sensitive System Information to an Unauthorized Control
  Sphere

## False-positive surface

- `expose_php = Off` (and `0` / `false` / `no`) is treated as safe.
- Any file containing the comment `; php-expose-php-allowed` or
  `# php-expose-php-allowed` is skipped wholesale.
- Lines starting with `;` (php.ini convention) or `#` are treated as
  comments and ignored.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS

$ python3 detector.py examples/bad/php.ini examples/bad/Dockerfile
examples/bad/php.ini:2:expose_php = On leaks PHP version via X-Powered-By
examples/bad/Dockerfile:2:Dockerfile echo sets expose_php = On" in php.ini
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
