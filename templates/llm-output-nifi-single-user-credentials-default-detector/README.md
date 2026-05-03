# llm-output-nifi-single-user-credentials-default-detector

## Purpose

Apache NiFi 1.14+ ships with a `single-user-provider` /
`SingleUserLoginIdentityProvider` and a corresponding
`SingleUserAuthorizer` so first-time users can log in. On a fresh start
NiFi will print a generated username and password to the log, but it is
extremely common for tutorials, blog posts, and LLM-generated configs
to either:

- hardcode the username `admin` and a known weak password into
  `login-identity-providers.xml` / `nifi.properties`, or
- leave `single-user-provider` as the active provider in production
  while exposing the UI on a public listener.

The result is a NiFi instance reachable from the network with a single
known credential and no real authorization model — anyone who logs in
gets full access to processors, controller services, and provenance.

When an LLM is asked "set up NiFi quickly" or "let me log in to NiFi",
it commonly proposes pinning `Username = admin` and a fixed `Password`
(often the literal placeholder from the docs) and selecting
`single-user-provider` as the active identity provider. The fix is to
use `ldap-provider` / `kerberos-provider` / `oidc` plus
`StandardManagedAuthorizer` for any non-developer instance.

## Signals (any one is sufficient to flag)

1. `login-identity-providers.xml` containing a `<provider>` block whose
   `<class>` is `org.apache.nifi.authentication.single.user.SingleUserLoginIdentityProvider`
   AND a `<property name="Username">` whose value is `admin` (case-insensitive)
   or empty.
2. Same XML with a `<property name="Password">` whose value is non-empty
   and **not** wrapped in a credential-store reference (i.e. the literal
   plaintext or bcrypt hash is checked into the file). We approximate
   "wrapped" by skipping values that start with `${` (env / property
   substitution) or are exactly empty.
3. `nifi.properties` containing
   `nifi.security.user.login.identity.provider=single-user-provider`
   AND `nifi.web.https.host=` set to a non-loopback value (`0.0.0.0`,
   empty, or any non-`127.*`/non-`localhost` literal).
4. `authorizers.xml` selecting `single-user-authorizer` as the active
   `Authorizer` AND the same file referencing
   `StandardManagedAuthorizer` only inside a commented-out block — i.e.
   single-user authz is the live policy.

## How the detector works

`detector.sh` performs targeted `grep`/`awk` passes per signal and
emits one `FLAG <signal-id> <file>:<lineno> <text>` line per finding.
It does not parse XML; it relies on the lexical surface of the
`<property name="…">value</property>` form NiFi uses, which is narrow
enough that real-world FP rates are low.

The detector never starts NiFi and never touches the network.

## False-positive risks

- A doc/comment that quotes the dangerous pattern verbatim will be
  flagged. Reviewers should glance at FLAG context.
- Signal 2 cannot tell a developer-only fixture from a production
  config. Combine with Signal 3 (public bind) for higher confidence.
- Signal 4's "live vs commented" check is line-based, not a real XML
  parser; nested CDATA shenanigans could fool it.

## Fixtures

- `fixtures/bad/`: 4 snippets covering each signal.
- `fixtures/good/`: 3 snippets — LDAP provider, env-substituted
  credentials, and loopback-only single-user dev config.

## Smoke

`bash smoke.sh` asserts `bad=4/4` flagged and `good=0/3` flagged.

## References

- CWE-798: Use of Hard-coded Credentials.
- CWE-521: Weak Password Requirements (when paired with the
  `single-user-provider` defaults).
