# llm-output-metabase-encryption-secret-key-weak-detector

Stdlib-Python detector that flags Metabase deployment configs
emitted by an LLM where ``MB_ENCRYPTION_SECRET_KEY`` is missing,
empty, a well-known placeholder, or shorter than 16 bytes.

## Why this exists

Metabase uses ``MB_ENCRYPTION_SECRET_KEY`` to encrypt the database
connection strings, OAuth client secrets, SAML keys, LDAP bind
credentials, and per-user API tokens stored in its application
database. Upstream is explicit: the key must be generated once
with a cryptographic RNG and stored out-of-band. Yet LLMs that
copy the "minimal" docker-compose example commonly:

- omit the variable entirely,
- leave it empty,
- fill it with a literal placeholder such as
  ``replace-me-with-a-strong-key``, or
- emit a too-short "looks random" string.

In each case, secrets in the application database are written
either in cleartext or under a predictable / low-entropy key. An
attacker who exfiltrates a DB dump trivially recovers every
connected source's credentials.

The detector flags four orthogonal regressions:

1. ``MB_ENCRYPTION_SECRET_KEY`` is set to an empty string.
2. ``MB_ENCRYPTION_SECRET_KEY`` is set to a known weak /
   placeholder literal (``changeme``, ``replace-me``,
   ``replace-me-with-a-strong-key``, ``metabase``, ``secret``,
   ``password``, ``0000000000000000``, ``1234567890abcdef``,
   etc., any case).
3. ``MB_ENCRYPTION_SECRET_KEY`` is set but shorter than the
   16-byte minimum recommended by upstream.
4. The file is clearly a Metabase deployment config (mentions
   ``metabase/metabase`` image, ``MB_DB_*`` keys, ``metabase.jar``
   entrypoint, ``MB_JETTY_*`` or ``MB_SITE_*`` keys) yet
   ``MB_ENCRYPTION_SECRET_KEY`` is never declared at all.

Files that do not look like a Metabase deployment are out of
scope.

CWE refs: CWE-321 (Use of Hard-coded Cryptographic Key),
CWE-798 (Use of Hard-coded Credentials),
CWE-1188 (Insecure Default Initialization of Resource).

Suppression: a top-level ``# metabase-encryption-secret-key-ok``
comment in the file disables all rules (use only for an isolated
lab deployment with no real connected sources).

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
detector.py                              # the rule engine (stdlib only)
run_example.py                           # worked example, runs all bundled samples
examples/
  bad_1_empty.txt                        # MB_ENCRYPTION_SECRET_KEY=""
  bad_2_placeholder.txt                  # value is "replace-me-with-a-strong-key"
  bad_3_too_short.txt                    # 8-char value, below 16-byte floor
  bad_4_missing.txt                      # Metabase compose with no key declared
  good_1_strong_key.txt                  # 32-byte base64 key
  good_2_hex_key.txt                     # 16-byte hex key (at the minimum)
  good_3_unrelated_config.txt            # no Metabase markers, out of scope
  good_4_suppressed.txt                  # suppression marker applied
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_empty.txt: FLAG (1 finding(s))
    L13: MB_ENCRYPTION_SECRET_KEY is set to an empty string ...
  bad_2_placeholder.txt: FLAG (1 finding(s))
    L6: MB_ENCRYPTION_SECRET_KEY is a well-known placeholder ...
  bad_3_too_short.txt: FLAG (1 finding(s))
    L4: MB_ENCRYPTION_SECRET_KEY is shorter than 16 bytes ...
  bad_4_missing.txt: FLAG (1 finding(s))
    Lx: MB_ENCRYPTION_SECRET_KEY is not declared on a Metabase deployment ...

== good samples (should each produce 0 findings) ==
  good_1_strong_key.txt: ok (0 finding(s))
  good_2_hex_key.txt: ok (0 finding(s))
  good_3_unrelated_config.txt: ok (0 finding(s))
  good_4_suppressed.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/4
RESULT: PASS
```

## Limitations

- Regex-based; assumes env-var-style consumption (compose, k8s
  ConfigMap, systemd EnvironmentFile, raw shell). Wrappers that
  translate a different key name into ``MB_ENCRYPTION_SECRET_KEY``
  need to render the final env first.
- The 16-byte floor is a length heuristic, not an entropy
  measurement; a 16-char string of all ``a`` will pass length but
  is still terrible. The literal denylist catches the most common
  trivially-weak values, but not arbitrary low-entropy keys.
- Java properties files (``-D`` JVM args) are not parsed.
- Configs that split the key into a separate Secret manifest must
  be concatenated with the rest of the deployment before scanning,
  otherwise rule 4 will fire on the Deployment manifest alone.
