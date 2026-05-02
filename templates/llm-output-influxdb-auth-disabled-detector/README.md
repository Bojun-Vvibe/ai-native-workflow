# llm-output-influxdb-auth-disabled-detector

Detect InfluxDB v1 (`influxdb.conf`) and v2 / OSS env-var snippets that ship
the database with HTTP authentication turned off, the legacy admin UI
re-enabled, or the profiling endpoint exposed without auth. These are
classic LLM "just get it running" patterns — and InfluxDB binds to the
HTTP port on every interface by default, so disabling auth means an
unauthenticated read/write line-protocol endpoint reachable from anything
that can route to the host.

## What this catches

| Rule | Pattern | Why it matters |
|------|---------|----------------|
| 1 | `[http]` block with `auth-enabled = false` | Anyone reaching `:8086` can `CREATE/DROP DATABASE`, write series, read everything |
| 2 | `pprof-enabled = true` with no `auth-enabled = true` | Profiling endpoint leaks goroutine/heap details and accepts CPU profile triggers without a credential |
| 3 | Env-var form `INFLUXDB_HTTP_AUTH_ENABLED=false` | Same as rule 1, just expressed via the official Docker image's env contract |
| 4 | v2 `--http-bind-address 0.0.0.0:8086` paired with a literal `--password <value>` flag | LLM-generated quickstart leaks creds AND binds the API to every interface |
| 5 | Uncommented `[admin]` block with `enabled = true` | The legacy admin UI was removed in 1.3 because it shipped with no authentication; resurrecting it via copy-pasted ancient configs re-introduces that hole |

Commented references (`# auth-enabled = false`) are deliberately ignored so
that documentation warning *against* the insecure default does not trip the
detector.

## What bad LLM output looks like

```
[http]
  enabled = true
  bind-address = ":8086"
  auth-enabled = false
```

```
INFLUXDB_HTTP_AUTH_ENABLED=false
```

```
[admin]
  enabled = true
  bind-address = ":8083"
```

## What good LLM output looks like

```
[http]
  enabled = true
  bind-address = "127.0.0.1:8086"
  auth-enabled = true
  pprof-enabled = false
```

## Sample layout

```
samples/
  bad/   # ≥3 files; every file MUST be flagged
  good/  # ≥3 files; no file may be flagged
```

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Exits `0` only when every `bad/*` is flagged and no `good/*` is.

## Verification

```
$ bash detect.sh samples/bad/* samples/good/*
BAD  samples/bad/01-auth-enabled-false.conf
BAD  samples/bad/02-env-auth-false.env.txt
BAD  samples/bad/03-pprof-no-auth.conf
BAD  samples/bad/04-legacy-admin-ui.conf
GOOD samples/good/01-auth-enabled-true.conf
GOOD samples/good/02-env-auth-true.env.txt
GOOD samples/good/03-warning-snippet.conf
bad=4/4 good=0/3 PASS
```

## Recommended fix when this fires

1. Set `auth-enabled = true` in the `[http]` block (or
   `INFLUXDB_HTTP_AUTH_ENABLED=true` for the Docker image).
2. Create an admin user with `influx` CLI (`CREATE USER ... WITH ALL PRIVILEGES`)
   *before* enabling auth, otherwise you will lock yourself out.
3. Bind to a private interface (`bind-address = "127.0.0.1:8086"` or a VPC
   address), not `:8086` / `0.0.0.0:8086`.
4. Leave `pprof-enabled = false` in production, or guard it behind a reverse
   proxy that enforces auth.
5. Never set `[admin] enabled = true` — that UI was removed and any config
   re-enabling it is from a pre-1.3 era.
