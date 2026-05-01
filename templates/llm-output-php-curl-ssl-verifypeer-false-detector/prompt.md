# prompt — llm-output-php-curl-ssl-verifypeer-false-detector

You are reviewing PHP source for **disabled libcurl TLS certificate
validation** (CWE-295 / CWE-297). For every reviewed file, walk the
file and flag each occurrence of:

1. `curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, <V>)` where `<V>` is a
   falsy literal: `false`, `FALSE`, `False`, `null`, `NULL`, `Null`,
   `0`, `"0"`, `'0'`, `"false"`, `'false'`.
2. `curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, <V>)` where `<V>` is a
   zero literal: `false`, `FALSE`, `False`, `0`, `"0"`, `'0'`.
3. The same options appearing as `=>` keys with the same falsy /
   zero values inside a `curl_setopt_array($ch, [ ... ])` literal.

Do **not** flag:

* Code where the option is set to a truthy value (`true`, `1`, `2`).
* Code that only sets `CURLOPT_CAINFO` / `CURLOPT_CAPATH`.
* The option name appearing inside a string literal or a comment
  (`//`, `#`, `/* */`).
* Any line that carries a `// llm-allow:php-curl-tls` (or `#`-style)
  suppression marker, or any statement / array literal that contains
  the marker anywhere within its bounds.
* Indirect cases (variable for the option list, defined constant for
  the value). These are out of scope for this detector.

For each finding emit a single line of the form

```
<path>:<line>: <code>: <reason>: <snippet>
```

where `<code>` is one of `php-curl-verifypeer-false`,
`php-curl-verifyhost-zero`, `php-curl-setopt-array-verifypeer-false`,
`php-curl-setopt-array-verifyhost-zero`. Exit non-zero if any finding
is emitted.

The fix is **never** "leave the flag off"; it is to provision the
correct CA bundle (`CURLOPT_CAINFO`) or hostname, and to keep
`CURLOPT_SSL_VERIFYPEER => true`, `CURLOPT_SSL_VERIFYHOST => 2`.
