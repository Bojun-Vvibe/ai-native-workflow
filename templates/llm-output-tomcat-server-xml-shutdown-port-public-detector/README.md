# llm-output-tomcat-server-xml-shutdown-port-public-detector

Static lint that flags Apache Tomcat `server.xml` files where the
top-level `<Server>` element exposes its **shutdown port** to non-
loopback callers while keeping the documented default magic word
(`SHUTDOWN`).

Tomcat's `<Server port="N" shutdown="WORD">` element opens a TCP
listener (default port `8005`) that, when it receives the plaintext
`WORD` followed by a newline, gracefully stops the JVM. Two common
LLM-generated mistakes turn this into a remote DoS / takedown
primitive:

1. `shutdown="SHUTDOWN"` left at the documented default — anyone who
   can reach the port can `echo SHUTDOWN | nc host 8005` and stop
   the server.
2. The `<Server>` element omits `address=` (Tomcat then binds on
   non-loopback) or explicitly sets `address="0.0.0.0"` /
   `address="::"`.

The combination of (1) + (2) is the exposure this detector flags.

LLM-generated `server.xml` files routinely copy the documented
default verbatim and forget that production Tomcat installs typically
restrict `address` to loopback or set `port="-1"` to disable the
listener entirely.

## What it catches

- First `<Server ...>` element in the file (attributes may span
  multiple lines).
- `port="-1"` → safe, listener disabled.
- `shutdown="SHUTDOWN"` (literal, case-sensitive — Tomcat compares
  literally) is treated as the default magic word.
- Missing `address=` attribute is treated as "binds non-loopback".
- `address` must be one of `127.0.0.1`, `localhost`, `::1`,
  `0:0:0:0:0:0:0:1` to be considered loopback-safe.
- A non-default magic word combined with a non-loopback bind is also
  flagged (lower-severity reminder that the "secret" word is now on
  the wire).

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function
- [CWE-749](https://cwe.mitre.org/data/definitions/749.html):
  Exposed Dangerous Method or Function
- [CWE-16](https://cwe.mitre.org/data/definitions/16.html):
  Configuration

## False-positive surface

- Embedded Tomcat behind a strict host firewall that drops 8005 —
  still flagged statically; suppress per file with the comment
  string `tomcat-shutdown-port-reviewed` anywhere in the file (the
  detector does a literal substring check so any wrapper, e.g.
  `<!-- tomcat-shutdown-port-reviewed: ticket OPS-1234 -->`, works).
- `port="-1"` (listener disabled) is treated as safe.
- Loopback bind with the default magic word and the default `8005`
  port is treated as safe (the canonical "everything default but
  loopback-only" deployment).

## Worked example

Live run:

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

Per-bad-file output:

```
$ python3 detector.py examples/bad/01-default-no-address.server.xml
examples/bad/01-default-no-address.server.xml:2:<Server port="8005" shutdown="SHUTDOWN"> with no address= attribute — default shutdown command reachable on non-loopback bind

$ python3 detector.py examples/bad/02-bind-wildcard.server.xml
examples/bad/02-bind-wildcard.server.xml:2:<Server port="8005" shutdown="SHUTDOWN" address="0.0.0.0"> — default shutdown command reachable on non-loopback address

$ python3 detector.py examples/bad/03-multiline-ipv6-wildcard.server.xml
examples/bad/03-multiline-ipv6-wildcard.server.xml:2:<Server port="8005" shutdown="SHUTDOWN" address="::"> — default shutdown command reachable on non-loopback address

$ python3 detector.py examples/bad/04-non-default-word-but-public-bind.server.xml
examples/bad/04-non-default-word-but-public-bind.server.xml:2:<Server port="8005" shutdown="StopMeButNotReally" address="10.0.0.42"> — non-default magic word but bound to non-loopback; review whether the magic word is actually secret
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag (4 files: missing `address`,
  IPv4 wildcard, IPv6 wildcard via multiline tag, non-default word
  with public bind).
- `examples/good/` — expected to pass clean (3 files: `port="-1"`,
  loopback bind, suppression marker).
