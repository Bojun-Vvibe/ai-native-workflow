# llm-output-solr-no-auth-detector

Static lint that flags Apache Solr configurations and launch commands
that expose the Admin UI on a network-reachable interface without an
authentication plugin loaded.

## Background

Solr ships with no authentication. The upstream
[Authentication and Authorization Plugins][solr-auth] guide describes
two safe postures:

1. Drop a `security.json` next to Solr Home (or upload one to ZooKeeper
   in cloud mode) that loads `BasicAuthPlugin` (or another plugin) and
   defines at least one credential.
2. If you intentionally run an unauthenticated dev instance, bind it
   to loopback only via `SOLR_JETTY_HOST=127.0.0.1` /
   `-Djetty.host=127.0.0.1`.

LLM-generated Solr snippets routinely break both invariants at once:
they either ship a `security.json` with the `authentication` block
deleted / set to `{}`, set `SOLR_JETTY_HOST=0.0.0.0`, or run
`docker run -p 8983:8983 solr` with no mounted `security.json`. Any of
these makes the Admin UI — which can read, write, and trigger config
API operations — usable by anyone who can route to port 8983.

[solr-auth]: https://solr.apache.org/guide/solr/latest/deployment-guide/authentication-and-authorization-plugins.html

## What it catches

- `security.json` with no `authentication` block, an empty
  `authentication` block, or an `authentication` block with no
  `class` field.
- `SOLR_JETTY_HOST=0.0.0.0` / `::` / `*` in `solr.in.sh`,
  Dockerfiles, env files, or shell scripts.
- `-Dhost=0.0.0.0` / `-Djetty.host=0.0.0.0` flags in launch commands.
- `bin/solr start` invocations with no loopback `-Dhost=` flag.
- `docker run … solr[:tag]` invocations with no `-p 127.0.0.1:8983:…`
  loopback binding *and* no mounted `security.json`.

## What it does *not* catch

This is a static check; it cannot tell whether a `security.json` that
*looks* well-formed is actually uploaded to ZooKeeper, or whether
firewall rules in front of the host narrow the exposure. Pair with
runtime probes against `/solr/admin/info/system`.

## Suppression

Add the comment marker `solr-no-auth-allowed` to suppress findings
in a fixture file.

## Usage

```sh
python3 detector.py path/to/security.json path/to/solr.in.sh
```

Exit code is the number of findings.

## Verify

```sh
bash verify.sh
```

Prints `bad=N/N good=0/M` and `PASS` when every bad fixture fires
and every good fixture is clean.
