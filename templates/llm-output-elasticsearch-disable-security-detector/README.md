# llm-output-elasticsearch-disable-security-detector

Static lint that flags Elasticsearch / OpenSearch node configs which
turn off the built-in security stack (authentication, TLS, audit) on a
node that is not pinned to loopback.

LLM-generated `elasticsearch.yml` / `opensearch.yml` files routinely
copy in the "just make it work" snippet from old StackOverflow answers:

```yaml
network.host: 0.0.0.0
xpack.security.enabled: false
```

That shape ships an unauthenticated cluster on every interface. Real
incidents:

- Multiple public reports of unauthenticated Elasticsearch clusters
  being scanned, ransomed (the "Meow" wave, 2020) and used as data-
  exfiltration buckets.
- Default-disabled security was the reason Elastic flipped the switch
  in 7.x to make basic security free and on-by-default
  ([Elastic security-on-by-default announcement][elastic-on]).
- OpenSearch ships a security plugin that some operators "fix" by
  disabling (`plugins.security.disabled: true`) — see the OpenSearch
  Security advisories list for what that opens up.

[elastic-on]: https://www.elastic.co/blog/security-for-elasticsearch-is-now-free

## What it catches

- `xpack.security.enabled: false` (any of false/no/off/0).
- `xpack.security.transport.ssl.enabled: false`.
- `xpack.security.http.ssl.enabled: false`.
- `plugins.security.disabled: true` (OpenSearch).
- `plugins.security.ssl.http.enabled: false` (OpenSearch).
- Anonymous user mapped to a privileged role
  (`superuser` / `all_access` / `kibana_admin`).
- Adds a TRIFECTA finding when any of the above co-occurs with a
  non-loopback `network.host` / `http.host` / `transport.host`.

The flattener understands both shapes that show up in the wild:

```yaml
xpack.security.enabled: false
```

and

```yaml
xpack:
  security:
    enabled: false
```

## CWE / advisory references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html): Missing
  Authentication for Critical Function.
- [CWE-319](https://cwe.mitre.org/data/definitions/319.html): Cleartext
  Transmission of Sensitive Information (SSL disabled).
- [CWE-732](https://cwe.mitre.org/data/definitions/732.html): Incorrect
  Permission Assignment for Critical Resource (anonymous → superuser).

## False-positive surface

- Local-laptop sandboxes that bind only to `127.0.0.1` / `::1` and
  intentionally run security-off. Suppress per file with a comment
  containing `es-no-security-allowed`.
- CI-only ephemeral fixtures: same suppression marker.
- Production configs that legitimately set `network.host: _local_`
  (loopback) are treated as safe even if `xpack.security.enabled: true`
  is missing.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of findings emitted.
- `verify.sh` — runs every fixture in `examples/bad` and `examples/good`
  and reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — must trip the detector.
- `examples/good/` — must run clean.

## Verification

Output of `bash verify.sh` on this checkout:

```
bad=4/4 good=0/3
PASS
```
