# llm-output-influxdb-auth-enabled-false-detector

Detects InfluxDB 1.x configurations where the HTTP API has
authentication explicitly disabled on a publicly reachable bind —
the exact shape that LLM "give me a quick InfluxDB I can hit from
Grafana" snippets emit.

## Why this matters

InfluxDB 1.x ships `influxdb.conf` with the `[http]` section
defaulting to `auth-enabled = false` and `bind-address = ":8086"`
(every interface). When users hit a 401 from a fresh install and ask
an assistant "how do I make `curl` and Grafana work without setting
up users", the canonical wrong answer is "set `auth-enabled = false`
in `[http]`".

That single line on a publicly bound listener leaves an unauthenticated
database server on the network with **read, write, and admin** all
open: `SHOW DATABASES`, `DROP DATABASE`, `CREATE USER`, time-series
ingest, and metadata queries are all anonymous. There is no
read-only fallback — auth is binary.

This detector flags the `(public bind) + (auth-enabled = false) +
([http] enabled)` triple.

## Rules

A finding is emitted when ALL three hold:

1. **`[http]` auth disabled.** The `[http]` section sets
   `auth-enabled = false` (literal, with optional whitespace, with
   optional inline comment). A missing `auth-enabled` key is NOT
   flagged — we only flag when the operator explicitly opts out.
2. **`[http]` enabled.** Either `enabled = true` or the key is
   absent (the binary default is `enabled = true`). `enabled = false`
   suppresses.
3. **Public bind.** `bind-address` is unset (binary default
   `:8086`), empty, `:8086`, `0.0.0.0:...`, `[::]:...`, or any
   non-loopback host/IP. `127.0.0.1:...`, `[::1]:...`, and
   `localhost:...` are treated as loopback-only and not flagged.

A line containing the marker `# influxdb-auth-disabled-allowed`
suppresses the finding for the whole file (use this for intentional
network-isolated lab sandboxes).

## Out of scope

* InfluxDB 2.x token-based auth misconfig (different config schema —
  `influxd.toml`, no `auth-enabled` key).
* Grafana datasource credentials hardcoded in dashboards.
* Reverse-proxy auth in front of InfluxDB (the detector is a
  conservative file-local check; it cannot see your nginx).

## Run

```
python3 detector.py examples/bad/01_default_disabled_default_bind.conf
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Verified output

```
$ ./verify.sh
bad=4/4 good=0/4
PASS

$ python3 detector.py examples/bad/01_default_disabled_default_bind.conf
examples/bad/01_default_disabled_default_bind.conf:14:InfluxDB [http] auth-enabled = false on a non-loopback bind-address (":8086") — unauthenticated read/write/admin

$ python3 detector.py examples/bad/02_explicit_zero_bind.conf
examples/bad/02_explicit_zero_bind.conf:7:InfluxDB [http] auth-enabled = false on a non-loopback bind-address ("0.0.0.0:8086") — unauthenticated read/write/admin

$ python3 detector.py examples/bad/03_v6_wildcard_bind.conf
examples/bad/03_v6_wildcard_bind.conf:4:InfluxDB [http] auth-enabled = false on a non-loopback bind-address ("[::]:8086") — unauthenticated read/write/admin

$ python3 detector.py examples/bad/04_routable_host_bind.conf
examples/bad/04_routable_host_bind.conf:5:InfluxDB [http] auth-enabled = false on a non-loopback bind-address ("metrics.example.internal:8086") — unauthenticated read/write/admin

$ for f in examples/good/*; do python3 detector.py "$f"; done
$  # (no output, exit 0 each — all four are correctly silent)
```
