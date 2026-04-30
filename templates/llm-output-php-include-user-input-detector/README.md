# llm-output-php-include-user-input-detector

Static detector for the PHP local-file-inclusion (LFI) anti-pattern
where `include`, `include_once`, `require`, or `require_once` is given
a target expression that references a request superglobal
(`$_GET`, `$_POST`, `$_REQUEST`, `$_COOKIE`, `$_FILES`, `$_SERVER`)
without any visible mitigation.

Why an LLM emits this: PHP's path-based router pattern is heavily
represented in older training data, and the simplest "router" is
`include $_GET['page'] . ".php";`. The trailing `.php` is *not* a
mitigation — `..%00` and similar tricks have historically defeated it,
and traversal (`../../etc/passwd`) defeats it absolutely if the
attacker can omit the suffix or PHP version permits null-byte
truncation. This detector flags the *shape*, not the suffix.

## What this flags

A finding is emitted whenever an `include` / `include_once` /
`require` / `require_once` target expression contains a reference to
one of the tainted superglobals AND none of these mitigation hints
appear in the same expression:

* `basename(`
* `realpath(`
* `in_array(`
* `array_key_exists(`
* `preg_match(`
* `hash_equals(`
* `filter_var(`

Both call form (`include($_GET['p'])`) and statement form
(`include $_GET['p'];`) are recognized.

Suppress with `// llm-allow:php-include-tainted` on the same logical
line.

PHP `//`, `#`, and `/* */` comments and string literal interiors are
masked before scanning, so docstring examples don't fire.

The detector also extracts fenced `php` / `phtml` code blocks from
Markdown.

## CWE references

* **CWE-98**: Improper Control of Filename for Include/Require
  Statement in PHP Program ('PHP Remote File Inclusion').
* **CWE-22**: Improper Limitation of a Pathname to a Restricted
  Directory ('Path Traversal').
* **CWE-829**: Inclusion of Functionality from Untrusted Control
  Sphere.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/` and `examples/good/` for fixtures.

## Important: this is a *detector*, not an exploit

The fixtures contain only minimal pseudo-code patterns sufficient for
the regex-level scanner to fire. They are not weaponized payloads and
they do not constitute a working LFI tool. The goal is to let
operators scan LLM-generated PHP and **fix** the pattern before it
reaches production.
