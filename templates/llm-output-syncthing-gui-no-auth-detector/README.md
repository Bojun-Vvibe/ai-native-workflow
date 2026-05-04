# llm-output-syncthing-gui-no-auth-detector

Stdlib-Python detector that flags Syncthing configurations from
LLM output that leave the GUI / REST API without authentication
while binding to a non-loopback address.

## Why this exists

Syncthing's GUI is more than a status page: the REST API can add
or remove devices, accept new shared folders, schedule rescans,
and read every byte of every shared folder. The upstream defaults
are deliberately conservative — the GUI binds to ``127.0.0.1:8384``
and an API key must be presented for any mutating call.

LLMs that emit a "container-friendly" config tend to override the
bind to ``0.0.0.0`` so the host's port mapping reaches the
container, but forget to enable the ``<gui>`` ``user`` /
``password`` pair or to seed a fresh ``<apikey>``. The result is a
fully-open file-share control panel.

The detector parses ``config.xml`` blobs (and ``STGUIADDRESS`` /
``STGUIAPIKEY`` env-var snippets) and flags four orthogonal
regressions:

1. ``<gui>`` element bound to ``0.0.0.0`` / ``[::]`` / a non-loopback
   IP with no ``<user>`` child.
2. ``<gui>`` bound publicly with an empty ``<password>`` element.
3. ``<gui>`` bound publicly with no ``<apikey>`` element (or empty).
4. ``STGUIADDRESS`` env-var bound publicly while ``STGUIAPIKEY`` is
   unset or empty.

Loopback values (``127.*``, ``::1``, ``localhost``) are treated as
out of scope: the detector only fires when the GUI is reachable
beyond the host itself.

CWE refs: CWE-306 (Missing Authentication for Critical Function),
CWE-1188 (Insecure Default Initialization of Resource).

Suppression: a top-level ``<!-- syncthing-gui-no-auth-ok -->`` XML
comment, or a ``# syncthing-gui-no-auth-ok`` shell comment, disables
all rules (use only for an isolated single-host deployment that is
firewalled off the network).

## API

```python
from detector import scan
findings = scan(open("config.xml").read())
# findings is a list of (line_number, reason) tuples; empty == clean.
```

CLI:

```
python3 detector.py path/to/config.xml [more.env ...]
```

Exit code = number of files with at least one finding.

## Layout

```
detector.py                          # the rule engine (stdlib only)
run_example.py                       # worked example, runs all bundled samples
examples/
  bad_1_public_no_user.txt           # 0.0.0.0 bind, no <user>
  bad_2_public_empty_password.txt    # [::] bind, empty <password>
  bad_3_public_no_apikey.txt         # 0.0.0.0 bind, no <apikey>
  bad_4_env_addr_no_apikey.txt       # STGUIADDRESS=0.0.0.0:..., STGUIAPIKEY=""
  good_1_loopback_full_auth.txt      # 127.0.0.1, all auth set
  good_2_public_full_auth.txt        # 0.0.0.0 bind, full credentials
  good_3_unrelated_config.txt        # not a Syncthing config
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_public_no_user.txt: FLAG (1 finding(s))
    L7: <gui> bound publicly to '0.0.0.0:8384' with no <user> element (GUI / REST API reachable without basic-auth credentials)
  bad_2_public_empty_password.txt: FLAG (1 finding(s))
    L9: <gui> bound publicly to '[::]:8384' with empty <password> (basic-auth accepts any credential)
  bad_3_public_no_apikey.txt: FLAG (1 finding(s))
    L8: <gui> bound publicly to '0.0.0.0:8384' without an <apikey> (mutating REST endpoints have no API-key gate)
  bad_4_env_addr_no_apikey.txt: FLAG (1 finding(s))
    L5: STGUIADDRESS='0.0.0.0:8384' binds publicly while STGUIAPIKEY is unset or empty (REST API has no auth gate)

== good samples (should each produce 0 findings) ==
  good_1_loopback_full_auth.txt: ok (0 finding(s))
  good_2_public_full_auth.txt: ok (0 finding(s))
  good_3_unrelated_config.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/3
RESULT: PASS
```

## Limitations

- Regex-based XML parsing — handles the well-formed shapes that
  Syncthing actually emits but is not a general XML parser.
  Configs that use namespaces, CDATA sections, or attribute-only
  encodings will not be recognised.
- The XML and env-var rules are evaluated independently. A single
  deployment that splits the address into ``config.xml`` and the
  api key into a separate ``stignore``-style file must be
  concatenated before scanning.
- The detector does not understand front-end auth proxies
  (Traefik forward-auth, oauth2-proxy, nginx basic-auth) sitting
  in front of Syncthing. If external auth is enforced, suppress
  the file with the comment marker.
- The detector is local-only: it does not resolve template values,
  pull secrets, or talk to the daemon.
