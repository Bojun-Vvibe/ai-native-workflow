# llm-output-java-ldap-injection-detector

Detect LDAP search filters built via Java string concatenation or
`String.format` and passed to a JNDI / `DirContext` /
`LdapContext` search call. CWE-90 (LDAP Injection).

## Why

LDAP search filters use a tiny RFC-4515 grammar where `*`, `(`, `)`,
`\`, and NUL are all metacharacters. Concatenating untrusted input
into a filter is the LDAP analogue of SQL injection: an attacker
controls the filter's structure, not just its values.

Typical LLM-generated mistake:

```java
String filter = "(&(uid=" + username + ")(objectClass=person))";
NamingEnumeration<SearchResult> r = ctx.search(base, filter, controls);
```

`username = "*)(uid=*))(|(uid=*"` turns the filter into
`(&(uid=*)(uid=*))(|(uid=*)(objectClass=person))`, which matches every
user. In an authentication path this is a full bypass.

The fix is to escape every untrusted value with the RFC-4515 escape
algorithm (commonly named `escapeLDAPSearchFilter` or
`Filter.encodeValue`), or — much better — use a parameterized API such
as `Filter.create("(&(uid={0})(objectClass=person))", username)` from
UnboundID, or build the filter from a parsed AST.

## What this flags

A `.search(...)` call on any identifier whose name ends in `Context`,
`Ctx`, `LdapContext`, or `DirContext` (case-insensitive), where the
filter argument (positional argument index 1, i.e. the second
argument) is one of:

1. A string literal containing `(` and `)` plus a `+` operator joining
   it to a non-literal expression on the same line.
2. A `String.format(...)` call whose format string contains `(` and a
   `%s` / `%d` / `%c` placeholder.
3. A bare identifier whose immediately preceding assignment in the
   file uses `+` to concatenate a literal containing `(` with another
   expression.

The detector also flags any direct call to `new SearchControls()`
followed within 30 lines by a `.search(...)` whose filter argument is
a `+`-concatenated string literal.

Per-line suppression: `// llm-allow:ldap-injection`.

## What this does NOT flag

- Calls where the filter is a pure string literal with no `+`.
- Calls where the filter argument is the result of a known-safe API:
  `Filter.create(...)`, `Filter.createANDFilter(...)`,
  `Filter.encodeValue(...)`, or any expression containing the literal
  text `escapeLDAPSearchFilter` / `escapeLdapFilter` /
  `Encode.forLdap` (OWASP Encoder).
- Strings inside `//` or `/* */` comments.

## False-positive notes

Identifier-based flow tracking is one assignment deep. If you stage
the unsafe filter through several variables the detector may miss it
(false negative) — that's intentional, since wider analysis would
require a real Java parser.

If a call site is verifiably safe (for example, the input is already
constrained to `[A-Za-z0-9]+` by an upstream regex) you can mark it
with `// llm-allow:ldap-injection`.

## Usage

    python3 detect.py <file_or_dir> [...]

Exit code is `1` if any findings, `0` otherwise. Stdlib only.
Recognized extensions: `.java`, `.md`, `.markdown` (Java fences in
Markdown are extracted and scanned).

## Verify

    bash verify.sh

Expected output: `bad findings: 6 (rc=1)`, `good findings: 0 (rc=0)`,
`PASS`.
