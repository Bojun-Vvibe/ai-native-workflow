# llm-output-vaultwarden-signups-allowed-detector

Stdlib-Python detector that flags Vaultwarden deployment configs
emitted by an LLM where ``SIGNUPS_ALLOWED=true`` is left in place
without any of the gating mitigations (domain allow-list, email
verification, admin token).

## Why this exists

Vaultwarden's default for ``SIGNUPS_ALLOWED`` is **true** so the
first-run UX can hand the deployer an account immediately. The
upstream README is explicit that this should be flipped to ``false``
once the operator account exists, but LLMs replicate the upstream
quickstart compose file verbatim — including ``SIGNUPS_ALLOWED=true``
— and ship the resulting deployment to the public internet, where
any visitor can:

- mint accounts that consume vault storage,
- trigger outbound invitation email at the operator's expense,
- exploit any future auth bug from an authenticated foothold.

The detector flags four orthogonal regressions:

1. ``SIGNUPS_ALLOWED=true`` with no ``SIGNUPS_DOMAINS_WHITELIST``
   set at all (registration open to any domain).
2. ``SIGNUPS_ALLOWED=true`` with ``SIGNUPS_DOMAINS_WHITELIST=""``
   (empty whitelist is treated as "all domains").
3. ``SIGNUPS_ALLOWED=true`` with ``SIGNUPS_VERIFY=false`` (no
   email verification gate on public sign-up).
4. ``SIGNUPS_ALLOWED=true`` with ``ADMIN_TOKEN=""`` or no
   ``ADMIN_TOKEN`` at all (no admin panel available to disable
   signups after bootstrap).

Truthy synonyms (``true`` / ``yes`` / ``1`` / ``on``, any case) are
all treated as enabled. Files that do not mention
``SIGNUPS_ALLOWED`` at all are out of scope (the detector does not
fire on unrelated configs even though Vaultwarden defaults to
``true`` when the env-var is absent).

CWE refs: CWE-1188 (Insecure Default Initialization of Resource),
CWE-862 (Missing Authorization).

Suppression: a top-level ``# vaultwarden-signups-allowed-ok``
comment in the file disables all rules (use only for a deliberate
public deployment such as a family-wallet demo).

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
detector.py                            # the rule engine (stdlib only)
run_example.py                         # worked example, runs all bundled samples
examples/
  bad_1_no_whitelist_no_admin.txt      # true + no whitelist + no admin token
  bad_2_empty_whitelist.txt            # true + WHITELIST=""
  bad_3_verify_disabled.txt            # true + SIGNUPS_VERIFY=false
  bad_4_empty_admin_token.txt          # true + ADMIN_TOKEN=""
  good_1_signups_disabled.txt          # SIGNUPS_ALLOWED=false
  good_2_full_lockdown.txt             # whitelist + verify + admin token
  good_3_no_signups_key.txt            # unrelated env file
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_no_whitelist_no_admin.txt: FLAG (2 finding(s))
    L8: SIGNUPS_ALLOWED=true with no SIGNUPS_DOMAINS_WHITELIST (public registration open to any email domain)
    L8: SIGNUPS_ALLOWED=true with no ADMIN_TOKEN set (no admin panel to disable signups after bootstrap)
  bad_2_empty_whitelist.txt: FLAG (1 finding(s))
    L4: SIGNUPS_DOMAINS_WHITELIST is empty while SIGNUPS_ALLOWED=true (empty whitelist is treated as 'all domains')
  bad_3_verify_disabled.txt: FLAG (1 finding(s))
    L5: SIGNUPS_VERIFY=false with SIGNUPS_ALLOWED=true (no email verification gate on public sign-up)
  bad_4_empty_admin_token.txt: FLAG (1 finding(s))
    L9: ADMIN_TOKEN is empty while SIGNUPS_ALLOWED=true (admin panel disabled, cannot revoke open signups)

== good samples (should each produce 0 findings) ==
  good_1_signups_disabled.txt: ok (0 finding(s))
  good_2_full_lockdown.txt: ok (0 finding(s))
  good_3_no_signups_key.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/3
RESULT: PASS
```

## Limitations

- Regex-based; assumes env-var style consumed by the upstream
  ``vaultwarden`` binary (compose, k8s ConfigMap, systemd
  EnvironmentFile, raw shell). Custom wrappers that translate some
  other key into ``SIGNUPS_ALLOWED`` need to render the final env
  first.
- Configs that set ``SIGNUPS_ALLOWED`` and ``ADMIN_TOKEN`` in
  separate files (e.g. one ConfigMap + one Secret) must be
  concatenated before scanning, otherwise rule 4 will fire on the
  first file.
- The ``no SIGNUPS_ALLOWED at all`` case is intentionally
  out-of-scope: while Vaultwarden's actual default is ``true``, the
  detector cannot tell whether the env-var is set elsewhere in the
  deployment. Operators who want to enforce "explicit `false`
  everywhere" should pair this detector with a lint that requires
  the key to be present.
- The detector is local-only: it does not resolve template values,
  pull secrets, or talk to the daemon.
