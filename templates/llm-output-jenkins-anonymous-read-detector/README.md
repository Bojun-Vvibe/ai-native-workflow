# llm-output-jenkins-anonymous-read-detector

Static lint that flags Jenkins controller `config.xml` files which
grant anonymous (unsigned-in) users read or higher access — i.e. the
classic "Jenkins is browsable / world-administrable" misconfiguration.

Jenkins authorization is controlled by an `<authorizationStrategy>`
element. Several common shapes leave the controller readable, and
sometimes writable, by anyone who can reach the HTTP port. LLMs asked
to "set up Jenkins so my CI is browsable" routinely paste:

```xml
<authorizationStrategy class="hudson.security.FullControlOnceLoggedInAuthorizationStrategy">
  <denyAnonymousReadAccess>false</denyAnonymousReadAccess>
</authorizationStrategy>
```

…or, worse:

```xml
<authorizationStrategy class="hudson.security.AuthorizationStrategy$Unsecured"/>
```

…without flagging that the controller is now world-administrable.

## What it catches

Per file, the scanner reports a finding when any of the following
appear in the XML (XML comments are stripped first):

1. `<authorizationStrategy class="hudson.security.AuthorizationStrategy$Unsecured"/>`
2. `<authorizationStrategy class="hudson.security.LegacyAuthorizationStrategy"/>`
3. A `FullControlOnceLoggedInAuthorizationStrategy` block whose
   `<denyAnonymousReadAccess>` is `false` *or* missing entirely
   (Jenkins defaults to allowing anonymous read).
4. A matrix-style `<permission>...:anonymous</permission>` line
   granting any Jenkins permission ID to `anonymous`.

## What it does NOT flag

- `FullControlOnceLoggedInAuthorizationStrategy` with
  `<denyAnonymousReadAccess>true</denyAnonymousReadAccess>`.
- Matrix strategies that grant permissions only to `authenticated`
  or to named users.
- Lines suppressed with a trailing `<!-- jenkins-anon-ok -->` comment.
- Files containing `<!-- jenkins-anon-ok-file -->` anywhere.

## CWE references

- [CWE-284](https://cwe.mitre.org/data/definitions/284.html):
  Improper Access Control
- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function
- [CWE-287](https://cwe.mitre.org/data/definitions/287.html):
  Improper Authentication

## False-positive surface

- Read-only public dashboards that are intentionally exposed via a
  reverse proxy with its own auth: suppress with
  `<!-- jenkins-anon-ok-file -->`.
- A single anonymous read permission line that the operator
  consciously wants (e.g. open-source build status badges): suppress
  the specific line with `<!-- jenkins-anon-ok -->`.

## Verification

```text
$ ./verify.sh
bad=5/5 good=0/3
PASS
```

Per-file output:

```text
$ python3 detector.py examples/bad/01-unsecured/config.xml
examples/bad/01-unsecured/config.xml:7:AuthorizationStrategy$Unsecured: anyone can do anything

$ python3 detector.py examples/bad/04-full-missing-deny/config.xml
examples/bad/04-full-missing-deny/config.xml:6:FullControlOnceLoggedInAuthorizationStrategy without <denyAnonymousReadAccess>true</denyAnonymousReadAccess> (default allows anonymous read)

$ python3 detector.py examples/bad/05-matrix-anonymous-admin/config.xml
examples/bad/05-matrix-anonymous-admin/config.xml:6:matrix permission granted to anonymous: hudson.model.Hudson.Administer
examples/bad/05-matrix-anonymous-admin/config.xml:7:matrix permission granted to anonymous: hudson.model.Hudson.Read
examples/bad/05-matrix-anonymous-admin/config.xml:8:matrix permission granted to anonymous: hudson.model.Item.Build

$ python3 detector.py examples/good/01-full-deny-true/config.xml ; echo rc=$?
rc=0
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=Y_clean/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — 5 configs that MUST flag (Unsecured, Legacy,
  FullControl with deny=false, FullControl missing deny, matrix
  granting perms to anonymous).
- `examples/good/` — 3 configs that MUST stay clean (FullControl
  deny=true, matrix authenticated-only, matrix named-users-only).
