# llm-output-powerdns-api-key-weak-detector

A small detector that scans LLM-generated PowerDNS configuration
(`pdns.conf`, `recursor.conf`, and accompanying docker-compose
files) for weak / missing / placeholder HTTP API credentials and
permissive bind / ACL combinations.

## Problem

PowerDNS Authoritative and Recursor expose an HTTP API that is
the primary control plane: anyone holding the `api-key` can
add zones, dump records, change forwarding, or (recursor) rewrite
the resolver's view of DNS. The API is gated by:

- `api=yes` and `webserver=yes`,
- `api-key=<secret>`, and
- `webserver-address` / `webserver-allow-from` ACLs.

LLM-generated configs frequently:

- enable `api=yes` / `webserver=yes` and forget the `api-key=`
  line entirely,
- set `api-key=changeme` / `api-key=secret` and never rotate,
- bind `webserver-address=0.0.0.0` with
  `webserver-allow-from=0.0.0.0/0,::/0` (or no ACL at all).

## Detection logic

The detector treats the input as in scope when any PowerDNS
marker appears (`launch=`, `setuid=pdns` / `setgid=pdns`,
`config-dir=…pdns…`, the `powerdns/pdns-auth` /
`powerdns/pdns-recursor` image, the literal `pdns.conf` /
`recursor.conf`, or any of the keys
`api-key=` / `webserver-allow-from=` / `webserver-address=`).

Rules (all require `api=yes` or `webserver=yes`):

1. **No api-key** — the API/webserver is enabled but no
   `api-key=` line appears.
2. **Placeholder api-key** — `api-key=` is one of the known
   placeholder values (`changeme`, `secret`, `password`,
   `replace_me`, `1234`, `admin`, `pdns`, `powerdns`, `default`,
   …, empty string).
3. **Public bind + open ACL** — `webserver-address` is `0.0.0.0`
   / `::` / `*` AND `webserver-allow-from` is missing, empty, or
   `0.0.0.0/0,::/0`.
4. **Combined critical** — the bind is public AND the api-key is
   missing or a placeholder. The detector emits a separate
   `CRITICAL:` line so reviewers can grep for it.

## False-positive notes

- A `postgres` / `nginx` config that mentions the word `api` in a
  comment will not trigger; the input must contain a PowerDNS
  marker first.
- Long random-looking `api-key=` values pass.
- A pinned ACL such as `webserver-allow-from=10.0.0.0/8,192.168.0.0/16`
  passes even when bound on `0.0.0.0`.
- A top-level comment `# powerdns-api-ok` suppresses all rules;
  use only when the API listener is firewalled to a dedicated
  management network.
- The "no api-key" rule does not flag configs where neither
  `api=` nor `webserver=` is enabled — disabled API is fine
  without a key.

## Exit codes

- `0` — no findings.
- `N` (1..255) — number of input files that produced at least one
  finding.

## Usage

```bash
python3 detector.py /etc/powerdns/pdns.conf [more.conf ...]
```

## Worked example

```bash
python3 run_example.py
```

Expected:

```
summary: bad=4/4 good_false_positives=0/4
RESULT: PASS
```

## CWE references

- CWE-798 (Use of Hard-coded Credentials)
- CWE-306 (Missing Authentication for Critical Function)
- CWE-1188 (Insecure Default Initialization of Resource)
