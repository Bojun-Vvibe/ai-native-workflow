# llm-output-apache-traceenable-on-detector

Static lint that flags Apache httpd configurations shipping with the
HTTP `TRACE` method enabled.

The `TRACE` method echoes the request — including `Cookie` and
`Authorization` headers — back in the response body. Combined with a
script-injection vector this becomes Cross-Site Tracing (XST) and
allows attackers to exfiltrate `HttpOnly` cookies. Modern Apache ships
with `TraceEnable Off` as the recommended default; LLM-generated
`httpd.conf` / `apache2.conf` / vhost snippets and Dockerfiles
sometimes flip it back to `On`, often pasted from outdated tutorials:

```apache
TraceEnable On
```

```dockerfile
RUN echo "TraceEnable On" >> /usr/local/apache2/conf/httpd.conf
```

This detector flags those shapes while accepting:

- `TraceEnable Off` / `off` / `0`
- files containing `# apache-traceenable-allowed` for committed dev
  fixtures
- comment lines (`#` prefix)

## What it catches

- Apache: `TraceEnable On|extended|1|true|yes` at global or vhost
  scope.
- Dockerfile `RUN` lines that `sed` / `echo` `TraceEnable On` into
  `httpd.conf` / `apache2.conf`.

## CWE references

- [CWE-489](https://cwe.mitre.org/data/definitions/489.html):
  Active Debug Code
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html):
  Exposure of Sensitive Information to an Unauthorized Actor
- [CWE-693](https://cwe.mitre.org/data/definitions/693.html):
  Protection Mechanism Failure

## False-positive surface

- `TraceEnable Off` is treated as safe.
- Any file containing the comment `# apache-traceenable-allowed` is
  skipped wholesale.
- Lines starting with `#` are treated as comments and ignored.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
