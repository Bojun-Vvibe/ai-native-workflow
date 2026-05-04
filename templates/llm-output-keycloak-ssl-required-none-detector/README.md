# llm-output-keycloak-ssl-required-none-detector

Detect Keycloak realm configurations (JSON exports, YAML, Helm values,
`.env`, kcadm.sh bootstrap scripts) that set `sslRequired` to `none`.

## What this catches

Keycloak realms enforce a transport-security floor with the
`sslRequired` field. Allowed values:

| value      | meaning                                              |
| ---------- | ---------------------------------------------------- |
| `external` | (default) HTTPS required for non-private IP clients  |
| `all`      | HTTPS required for every client                      |
| `none`     | cleartext HTTP accepted from anywhere                |

When an LLM is asked to "make Keycloak work behind my reverse proxy"
or "fix the HTTPS required error in dev", it frequently returns a
realm export with `sslRequired: none`. Shipped to staging or prod,
this lets credentials, authorization codes, refresh tokens, and SSO
session cookies traverse cleartext links.

## Detector logic

`detector.py` is stdlib-only Python 3. It strips line comments
(`#` and `//`) so commented-out examples don't trigger, then matches
any of:

- JSON / YAML key/value:  `"sslRequired": "none"` or `sslRequired: none`
- env / `.properties`:    `KC_SSL_REQUIRED=none` or `KEYCLOAK_SSL_REQUIRED=none`
- kcadm.sh CLI flag:      `-s sslRequired=none` or `--set sslRequired=none`
- Helm-style override:    `realm.sslRequired=none`

Match → prints `BAD` and exits 1. Otherwise prints `GOOD` and exits 0.

## How to run

```bash
python3 detector.py bad/case-1.json    # -> BAD  (exit 1)
python3 detector.py good/case-1.json   # -> GOOD (exit 0)

bash worked-example.sh                 # runs all 7 fixtures + asserts
```

## Layout

```
detector.py
worked-example.sh
bad/
  case-1.json     # realm export with "sslRequired": "none"
  case-2.yaml     # YAML realm with sslRequired: none
  case-3.sh       # kcadm.sh bootstrap with -s sslRequired=none
  case-4.properties  # KEYCLOAK_SSL_REQUIRED=none in container env
good/
  case-1.json        # sslRequired: external (default)
  case-2.yaml        # sslRequired: all + commented-out historical "none"
  case-3.properties  # KEYCLOAK_SSL_REQUIRED=all + HTTP disabled
```

## Limitations

- Pure prose ("set sslRequired to none") is intentionally **not** a
  match; we only flag structured config / CLI / env assignments to
  reduce false positives in documentation.
- The detector does not parse JSON/YAML; a multi-line `sslRequired`
  value split across lines would be missed. In practice realm
  exports always emit it on one line.
