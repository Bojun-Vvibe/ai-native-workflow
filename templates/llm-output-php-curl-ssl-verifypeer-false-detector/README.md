# llm-output-php-curl-ssl-verifypeer-false-detector

Stdlib-only Python detector that flags **PHP** source where libcurl's
TLS certificate validation is disabled via `curl_setopt` /
`curl_setopt_array`:

* `CURLOPT_SSL_VERIFYPEER` set to a falsy value (`false`, `0`, `"0"`,
  `null`, `FALSE`, etc.)
* `CURLOPT_SSL_VERIFYHOST` set to `0` / `false` (the fully-disabled
  values; weak-but-not-zero `1` is intentionally not flagged here)

This is the canonical CWE-295 / CWE-297 (Improper Certificate
Validation) shape in PHP. Under "make this HTTPS request work in dev"
pressure, an LLM tends to write:

```php
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0);
```

instead of fixing the actual CA bundle / hostname mismatch.

## Why this exact shape

PHP's libcurl binding defaults to **on** for both `VERIFYPEER` and
`VERIFYHOST`. Disabling either one silently strips the
authentication half of TLS — the channel is still encrypted but no
longer bound to the server identity, so any on-path attacker can
impersonate the endpoint. The "fix" almost always belongs at the
trust-store layer (`CURLOPT_CAINFO` / `CURLOPT_CAPATH`), not at the
verification flag.

## What's flagged

1. **`php-curl-verifypeer-false`** —
   `curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, <falsy>)` direct call.
2. **`php-curl-verifyhost-zero`** —
   `curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0|false)` direct call.
3. **`php-curl-setopt-array-verifypeer-false`** — same as #1 but
   inside a `curl_setopt_array($ch, [ ... ])` array literal.
4. **`php-curl-setopt-array-verifyhost-zero`** — same as #2 but
   inside a `curl_setopt_array($ch, [ ... ])` array literal.

Falsy is recognized as: `false`, `FALSE`, `False`, `null`, `NULL`,
`Null`, `0`, `"0"`, `'0'`, `"false"`, `'false'`. Hostname zero is the
narrower set: `false`, `FALSE`, `False`, `0`, `"0"`, `'0'`.

Suppress with a trailing `// llm-allow:php-curl-tls` or
`# llm-allow:php-curl-tls` on the relevant `curl_setopt` line, or
anywhere within the same statement (semicolon-bounded) / array
literal.

## Safe shapes the detector deliberately leaves alone

* Default behavior — no `curl_setopt` for `VERIFYPEER` at all.
* `curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true)`.
* `curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2)` (the only correct
  non-default value).
* `CURLOPT_CAINFO` / `CURLOPT_CAPATH` overrides without touching the
  verify flags.
* String literals that *mention* the option name without calling
  `curl_setopt`.
* Any of the above appearing inside `//`, `#`, or `/* */` comments.

## CWE / standards

- **CWE-295**: Improper Certificate Validation.
- **CWE-297**: Improper Validation of Certificate with Host Mismatch.
- **OWASP A02:2021** — Cryptographic Failures.
- PHP manual: `CURLOPT_SSL_VERIFYPEER` (default `true` since
  curl 7.10) and `CURLOPT_SSL_VERIFYHOST` (default `2`).

## Limits / known false negatives

- We don't follow assignments: `$opts = [CURLOPT_SSL_VERIFYPEER =>
  false]; curl_setopt_array($ch, $opts);` is **not** flagged. Most
  LLM output uses the array literal directly at the call site.
- We don't follow constants: `define('NO_VERIFY', false);
  curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, NO_VERIFY);` is **not**
  flagged.
- `CURLOPT_SSL_VERIFYHOST` set to `1` (deprecated weak mode) is
  **not** flagged here — that's a separate, narrower discipline.

## Usage

```bash
python3 detect.py path/to/file.php
python3 detect.py path/to/dir/   # walks *.php, *.phtml, *.md, *.markdown
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Verify

```
$ bash verify.sh
bad=6/6 good=0/6
PASS
```

### Worked example — `python3 detect.py examples/bad/`

```
$ python3 detect.py examples/bad/
examples/bad/01_verifypeer_false.php:4: php-curl-verifypeer-false: ...
examples/bad/02_verifypeer_zero_and_verifyhost_zero.php:4: php-curl-verifypeer-false: ...
examples/bad/02_verifypeer_zero_and_verifyhost_zero.php:5: php-curl-verifyhost-zero: ...
examples/bad/03_setopt_array.php:5: php-curl-setopt-array-verifypeer-false: ...
examples/bad/03_setopt_array.php:6: php-curl-setopt-array-verifyhost-zero: ...
examples/bad/04_namespaced_constants.php:5: php-curl-verifypeer-false: ...
examples/bad/04_namespaced_constants.php:6: php-curl-verifyhost-zero: ...
examples/bad/05_verifypeer_string_zero.php:4: php-curl-verifypeer-false: ...
examples/bad/06_setopt_array_null.php:5: php-curl-setopt-array-verifypeer-false: ...
$ echo $?
1
```

### Worked example — `python3 detect.py examples/good/`

```
$ python3 detect.py examples/good/
$ echo $?
0
```

Layout:

```
examples/bad/
  01_verifypeer_false.php                       # direct call, false
  02_verifypeer_zero_and_verifyhost_zero.php    # both flags zeroed
  03_setopt_array.php                           # array form, both flags
  04_namespaced_constants.php                   # \CURLOPT_..., FALSE
  05_verifypeer_string_zero.php                 # "0" string falsy
  06_setopt_array_null.php                      # array form, null value
examples/good/
  01_default_verification.php                   # never sets the flag
  02_explicit_true.php                          # VERIFYPEER=true, HOST=2
  03_setopt_array_safe.php                      # array form, safe values
  04_string_mentions.php                        # token only in a string
  05_only_in_comments.php                       # bad code masked by //, #, /* */
  06_suppressed.php                             # explicit llm-allow marker
```
