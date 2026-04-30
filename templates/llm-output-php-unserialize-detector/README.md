# llm-output-php-unserialize-detector

Static detector for the PHP anti-pattern of feeding attacker-reachable
bytes into `unserialize()`.

`unserialize()` instantiates arbitrary objects and invokes their magic
methods (`__wakeup`, `__destruct`, `__toString`) on the resulting graph.
When the input is attacker-controlled, this is a classic PHP object
injection / RCE primitive.

```php
// dangerous — attacker controls the byte stream
$session = unserialize($_GET['session']);

// safer — JSON does not instantiate classes
$session = json_decode($_GET['session'], true);
```

## What this flags

The detector recognizes `unserialize(<arg>)` where the first positional
argument matches **any** of the following shapes:

* a PHP superglobal — `$_GET[...]`, `$_POST[...]`, `$_REQUEST[...]`,
  `$_COOKIE[...]`, `$_FILES[...]`, `$_SERVER[...]`, or
  `$HTTP_RAW_POST_DATA`;
* `file_get_contents('php://input')` (the canonical raw-body idiom)
  or `file_get_contents($_*[...])`;
* a bare variable whose name starts with one of the conventional
  "untrusted" prefixes — `$user_*`, `$untrusted_*`, `$payload`,
  `$body`, `$raw`, `$input`, `$cookie`, `$req`, `$request`, `$post`,
  `$get`, `$param(s)`;
* a chained decode wrapper (`base64_decode`, `gzuncompress`,
  `gzinflate`, `gzdecode`, `rawurldecode`, `urldecode`, `hex2bin`)
  around any of the above. This catches the common
  `unserialize(base64_decode($_GET['data']))` obfuscation.

The first argument is the only one inspected — passing
`['allowed_classes' => false]` as the second argument is **still
flagged**, because attacker-controlled serialized data is a denial-of-
service vector even when class instantiation is forbidden, and
`allowed_classes` itself has been bypass-prone historically.

PHP-aware token handling:

* `//`, `#`, and `/* ... */` comment bodies are blanked.
* `'...'`, `"..."` string-literal bodies are blanked.
* Heredoc and nowdoc bodies are blanked.

So a docstring or comment that mentions `unserialize($_GET['x'])` does
not produce a finding.

A finding is suppressed if the same logical line carries the marker
`llm-allow:php-unserialize` (typically inside a `//` comment).

The detector also extracts fenced `php` (or unlabeled) code blocks
from Markdown so that worked examples in docs are scanned.

## Safe alternatives

* For untrusted request data, use `json_decode()` / `json_encode()`.
* For internal trusted persistence, prefer dedicated formats such as
  `igbinary` only if you also authenticate the bytes (HMAC or signed
  envelope).
* If you genuinely must `unserialize()` arbitrary bytes, terminate the
  attack surface earlier by validating the byte stream against a
  signed envelope and pass `['allowed_classes' => [...]]` with an
  explicit allow-list of expected classes.

## CWE references

* **CWE-502**: Deserialization of Untrusted Data.
* **CWE-915**: Improperly Controlled Modification of Dynamically-
  Determined Object Attributes.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/` and `examples/good/` for the concrete fixtures.
