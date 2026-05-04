# llm-output-kibana-elasticsearch-username-elastic-default-detector

Detects Kibana configurations (`kibana.yml`, env files, compose
manifests, Kubernetes pod specs) that connect to Elasticsearch
using the built-in bootstrap superuser account `elastic`.

## Why this matters

`elastic` is the bootstrap superuser created on first
Elasticsearch start. It has cluster-wide unrestricted privileges
including the ability to read and rewrite the security index.
The Kibana docs explicitly recommend a dedicated
`kibana_system` service account with the minimum privileges
required to run Kibana.

When Kibana is wired as `elastic`:

- Every saved-object write, reporting job, Fleet enrolment, alert
  action and migration runs as full cluster superuser.
- Any Kibana RCE / SSRF / template-injection bug (several have
  shipped across 7.x and 8.x) becomes immediate full cluster
  takeover.
- The password is usually the one set by
  `elasticsearch-setup-passwords` and is widely shared among
  operators, so rotation is painful and frequently skipped.

This is a textbook CWE-250 (Execution with Unnecessary Privileges)
finding. Despite that, LLM-generated Kibana configs frequently
emit:

```yaml
elasticsearch.hosts: ["https://es01:9200"]
elasticsearch.username: "elastic"
elasticsearch.password: "changeme"
```

or the env-var equivalent:

```yaml
environment:
  ELASTICSEARCH_USERNAME: elastic
  ELASTICSEARCH_PASSWORD: changeme
```

## What's checked

For each file the detector flags:

1. YAML / properties key `elasticsearch.username` whose value is
   exactly `elastic` (case-insensitive, quotes stripped).
2. Inline env-var assignment `ELASTICSEARCH_USERNAME=elastic` or
   `ELASTICSEARCH_USERNAME: "elastic"` (docker-compose, `.env`,
   shell exports).
3. Two-line Kubernetes-style env entries:

   ```yaml
   - name: ELASTICSEARCH_USERNAME
     value: elastic
   ```

`elasticsearch.username: kibana_system` (the recommended account)
and any other non-`elastic` value are not flagged.

## Accepted (not flagged)

- `elasticsearch.username: kibana_system`
- `elasticsearch.username: kibana` (legacy dedicated account name)
- Any other identifier (e.g. `kibana_app`, `elasticadmin`,
  `elastic-prod`).
- Files containing the comment `# kibana-elastic-superuser-allowed`
  (intentional lab / single-node demo fixtures).

## Refs

- CWE-250: Execution with Unnecessary Privileges
- Elastic Stack Security: built-in users — `elastic` vs
  `kibana_system`
- OWASP A01:2021 Broken Access Control

## Usage

```
python3 detector.py path/to/kibana.yml [more.yml ...]
```

Exit code = number of flagged files (capped at 255). Findings
print as `<file>:<line>:<reason>`.
