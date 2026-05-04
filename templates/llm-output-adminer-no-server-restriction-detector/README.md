# llm-output-adminer-no-server-restriction-detector

Stdlib-Python detector that flags Adminer deployment configs
emitted by an LLM where the login form is left unrestricted (any
database server hostname accepted) and the container is exposed
beyond loopback.

## Why this exists

Adminer ships as a single PHP file. Out of the box, the login
form accepts an arbitrary ``server`` value, which means anyone
who can reach the Adminer URL can use it as a database client /
internal port scanner against any host the Adminer container can
route to. Upstream guidance is to either:

- run a customised ``index.php`` that constructs the ``Adminer``
  instance with one of the access-restriction plugin classes
  (``AdminerLoginServers``, ``AdminerRestrictAccess``,
  ``AdminerLoginPasswordLess``, ``AdminerLoginIp``), or
- bind Adminer to the loopback interface and front it with an
  auth-enforcing reverse proxy.

LLMs that copy the upstream "minimal" docker-compose example
verbatim almost never wire up a plugin, and they tend to publish
the Adminer port directly on ``0.0.0.0:8080``. The result is an
unauthenticated DB pivot host on whatever network reaches that
port.

The detector flags four orthogonal regressions on configs that
are clearly Adminer (mention the ``adminer`` image, the
``adminer.php`` file, or any ``ADMINER_*`` env key):

1. The Adminer port is published on a non-loopback host (compose
   ``ports:`` entry such as ``"8080:8080"``,
   ``"0.0.0.0:8080:8080"``, or any non-loopback IP bind) AND no
   plugin / restriction marker is present.
2. ``ADMINER_DEFAULT_SERVER`` is unset on a publicly-exposed
   deployment (default behaviour: free-form server field).
3. A custom ``index.php`` is mounted (or COPYed) but the blob
   does not include any ``AdminerLoginServers`` /
   ``AdminerRestrictAccess`` / ``AdminerLoginPasswordLess`` /
   ``AdminerLoginIp`` token.
4. ``ADMINER_PLUGINS`` is set but does not include any of the
   access-restriction plugins (``login-servers``,
   ``login-password-less``, ``restrict-access``, ``login-ip``).

Files that do not look like Adminer are out of scope.

CWE refs: CWE-306 (Missing Authentication for Critical Function),
CWE-918 (SSRF — Adminer can be coerced to connect to arbitrary
internal hosts), CWE-1188 (Insecure Default Initialization of
Resource).

Suppression: a top-level ``# adminer-server-restriction-ok``
comment in the file disables all rules (use only when an external
auth layer such as forward-auth via Traefik / nginx / oauth2-proxy
is enforced).

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
detector.py                                       # the rule engine (stdlib only)
run_example.py                                    # worked example
examples/
  bad_1_minimal_compose.txt                       # default compose, 8080 published, no plugin
  bad_2_plugins_no_restriction.txt                # ADMINER_PLUGINS without login-servers
  bad_3_custom_index_no_restriction.txt           # custom index.php with no restriction class
  bad_4_no_default_server.txt                     # public bind, no ADMINER_DEFAULT_SERVER
  good_1_login_servers_plugin.txt                 # ADMINER_PLUGINS=login-servers
  good_2_loopback_bind.txt                        # 127.0.0.1:8080 only
  good_3_custom_index_with_restriction.txt        # AdminerRestrictAccess wired up
  good_4_unrelated_config.txt                     # nginx config, no Adminer markers
```

## Worked example output

Captured from `python3 run_example.py`:

```
== bad samples (should each produce >=1 finding) ==
  bad_1_minimal_compose.txt: FLAG (1 finding(s))
    L10: Adminer is published beyond loopback (- "8080:8080") with no server-restriction plugin ...
  bad_2_plugins_no_restriction.txt: FLAG (2 finding(s))
    L1: ADMINER_PLUGINS set but contains no access-restriction plugin ...
    L10: Adminer is published beyond loopback ...
  bad_3_custom_index_no_restriction.txt: FLAG (2 finding(s))
    L1: Custom Adminer index.php is referenced but the file does not call AdminerLoginServers / AdminerRestrictAccess / AdminerLoginPasswordLess / AdminerLoginIp
    L10: Adminer is published beyond loopback ...
  bad_4_no_default_server.txt: FLAG (1 finding(s))
    L9: Adminer is published beyond loopback ...

== good samples (should each produce 0 findings) ==
  good_1_login_servers_plugin.txt: ok (0 finding(s))
  good_2_loopback_bind.txt: ok (0 finding(s))
  good_3_custom_index_with_restriction.txt: ok (0 finding(s))
  good_4_unrelated_config.txt: ok (0 finding(s))

summary: bad=4/4 good_false_positives=0/4
RESULT: PASS
```

## Limitations

- The publish-port heuristic only flags host ports in the
  3000-9999 range to avoid noise from unrelated published
  services in the same compose file. Adminer on, say, port 80 or
  20000 will not be detected as "publicly exposed" by rule 1.
- The custom-index.php rule looks at the same blob for
  restriction tokens; if the index.php is in a separate file that
  is not concatenated with the compose, rule 3 will fire. Either
  concatenate, or apply the suppression comment.
- ``ADMINER_PLUGINS`` is parsed by whitespace / comma splitting;
  shell-quoted oddities (e.g. plugins fetched at runtime by an
  entrypoint script) are not understood.
- Forward-auth at a reverse proxy is not visible in the Adminer
  config alone; suppress with the comment marker when that
  arrangement is in use.
- The detector does not inspect Kubernetes ``Service`` /
  ``Ingress`` manifests for exposure; the docker-compose
  ``ports:`` heuristic is the primary trigger.
