# llm-output-kibana-disable-security-detector

Detects LLM-generated Kibana configuration that disables the bundled
security plugin, leaving the Kibana UI (and any proxied Elasticsearch
operations) reachable without authentication.

## What is flagged

Kibana ships with X-Pack security enabled by default. Snippets pasted
out of LLMs frequently turn it off to "make the tutorial work":

* `xpack.security.enabled: false` in `kibana.yml`
* `XPACK_SECURITY_ENABLED=false` exported in shell / docker-compose
* `--xpack.security.enabled=false` passed to the `kibana` binary
* the legacy `xpack.security.authc.providers: anonymous` block with
  no credential requirement
* connecting to Elasticsearch with `elasticsearch.username: kibana`
  and `elasticsearch.password: changeme` (the original install
  default that survives in many tutorials)

Any single one of these landing on a network-reachable host turns the
Kibana instance into an open admin console.

## Suppression

Add the marker `kibana-no-auth-allowed` anywhere in the file (e.g. in
a comment) to silence the detector for an intentional lab fixture.

## Run

```
./verify.sh
```

Expected:

```
bad=4/4 good=0/3
PASS
```
