# llm-output-meilisearch-no-master-key-detector

Stdlib-Python detector that flags Meilisearch deployment configs
emitted by an LLM where the HTTP API is left unauthenticated because
`MEILI_MASTER_KEY` is missing, empty, too short, or because the
daemon is started in `MEILI_ENV=development` while bound to a
non-loopback address.

## Why this exists

Meilisearch's HTTP API is fully unauthenticated unless the server
is started with a master key of **at least 16 bytes**. From v1.0
the daemon refuses to boot in `MEILI_ENV=production` without one,
but `MEILI_ENV=development` (and the default of `development` in
many community charts) silently disables key validation and exposes
the search preview dashboard to anyone who can reach `:7700`.

LLMs replicate the upstream "quickstart" docker run line verbatim,
which omits the key entirely, then attach `-p 7700:7700` and a
public bind. The detector flags four orthogonal regressions:

1. `MEILI_HTTP_ADDR` (env) or `--http-addr` (CLI) is non-loopback
   and `MEILI_MASTER_KEY` / `--master-key` is absent.
2. `MEILI_MASTER_KEY=""` — explicit empty value, defeating
   "is set" presence checks in Helm templates.
3. `MEILI_MASTER_KEY` shorter than 16 bytes — Meilisearch logs a
   warning and falls through to dev-mode (no key validation).
4. `MEILI_ENV=development` while a non-loopback `MEILI_HTTP_ADDR`
   is set — exposes the unauthenticated search preview dashboard.

CWE refs: CWE-306 (Missing Authentication), CWE-521 (Weak
Password Requirements).

Suppression: a top-level `# meili-no-master-key-allowed` comment
in the file disables all rules (use only for local fixtures).

## API

```python
from detector import scan
findings = scan(open("docker-compose.yml").read())
# findings is a list of (line_number, reason) tuples; empty == clean.
```

CLI:

```
python3 detector.py path/to/compose.yml [more.env ...]
```

Exit code = number of files with at least one finding.

## Layout

```
detector.py                       # the rule engine (stdlib only)
run_example.py                    # worked example, runs all bundled samples
examples/
  bad_1_no_master_key.txt         # docker run with -e MEILI_HTTP_ADDR but no key
  bad_2_empty_master_key.txt      # MEILI_MASTER_KEY=""
  bad_3_short_master_key.txt      # 7-byte master key
  bad_4_dev_env_public_bind.txt   # MEILI_ENV=development + 0.0.0.0 bind
  good_1_full_config.txt          # 32-byte key + production env
  good_2_loopback_only.txt        # 127.0.0.1 bind, no key needed
  good_3_cli_flags.txt            # --master-key + --env production
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_no_master_key.txt: FLAG (1 finding(s))
    L4: MEILI_HTTP_ADDR=0.0.0.0:7700 is non-loopback but no MEILI_MASTER_KEY / --master-key is set (HTTP API is unauthenticated)
  bad_2_empty_master_key.txt: FLAG (1 finding(s))
    L3: MEILI_MASTER_KEY is set to an empty value (HTTP API is unauthenticated)
  bad_3_short_master_key.txt: FLAG (1 finding(s))
    L8: MEILI_MASTER_KEY is only 7 bytes; Meilisearch requires >=16 bytes and treats shorter keys as dev-mode (no key validation)
  bad_4_dev_env_public_bind.txt: FLAG (1 finding(s))
    L3: MEILI_ENV=development with non-loopback MEILI_HTTP_ADDR exposes the unauthenticated search preview dashboard

== good samples (should each produce 0 findings) ==
  good_1_full_config.txt: ok (0 finding(s))
  good_2_loopback_only.txt: ok (0 finding(s))
  good_3_cli_flags.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/3
RESULT: PASS
```

## Limitations

- Regex-based; assumes env-var or CLI flag style consumed by the
  upstream `meilisearch` binary. Custom wrappers that translate
  some other key (e.g. `SEARCH_API_KEY`) into `MEILI_MASTER_KEY`
  need to render the final env first.
- The 16-byte threshold matches the upstream check at the time of
  writing. If Meilisearch tightens the requirement, lift the
  literal in `detector.py`.
- The `MEILI_ENV=development` rule only fires when a non-loopback
  `MEILI_HTTP_ADDR` is present in the same blob. Configs that set
  the env in one file and the bind in another must be concatenated
  before scanning.
- The detector is local-only: it does not resolve template values,
  pull secrets, or talk to the daemon.
