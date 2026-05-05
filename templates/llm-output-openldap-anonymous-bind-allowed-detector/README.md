# llm-output-openldap-anonymous-bind-allowed-detector

Detect OpenLDAP (`slapd`) configurations that LLMs commonly emit without
disabling **anonymous bind**. Out of the box `slapd` accepts an anonymous
bind (an empty DN with empty password); a client can then probe the Root
DSE, enumerate the schema, and — depending on the ACL — read large parts
of the directory tree with no credentials at all. The hardening knobs
that close this off are:

- `slapd.conf` (legacy form): a global `disallow bind_anon` line, OR
  a per-database `require authc` (also accepts `strong` / `sasl`).
- cn=config / OLC LDIF form: `olcDisallows: bind_anon` on `cn=config`,
  OR `olcRequires: authc` on the database / frontend entry.
- Invocation form: `slapd ... -o disallow=bind_anon ...`.

When asked "set up an OpenLDAP server with users and groups", LLMs
routinely emit a working `slapd` config that omits all three. ACL-only
hardening (`access to ... by * none`) is not enough: the bind itself
still succeeds and the Root DSE is still readable.

This detector is orthogonal to the family of `*-no-auth` /
`*-default-credentials` detectors: those flag missing or shared
credentials, while this one flags the directory protocol's *anonymous*
mode being left enabled even when real credentials exist.

Related weaknesses: CWE-287 (Improper Authentication), CWE-1390 (Weak
Authentication), CWE-200 (Exposure of Sensitive Information to an
Unauthorized Actor).

## What bad LLM output looks like

Legacy `slapd.conf` with no `disallow` and no `require`:

```
database    mdb
suffix      "dc=example,dc=org"
rootdn      "cn=admin,dc=example,dc=org"
rootpw      {SSHA}placeholder
directory   /var/lib/openldap/openldap-data
```

cn=config LDIF that defines a database but never sets `olcDisallows` /
`olcRequires`:

```
dn: cn=config
objectClass: olcGlobal
cn: config

dn: olcDatabase={1}mdb,cn=config
olcSuffix: dc=example,dc=org
olcRootDN: cn=admin,dc=example,dc=org
```

cn=config LDIF that hardens with ACLs only — the anonymous bind itself
still succeeds:

```
olcAccess: {0}to dn.base="" by * read
```

A Dockerfile invocation with no `-o disallow=bind_anon` and no `-f` /
`-F` pointer to an external config:

```dockerfile
CMD ["slapd", "-d", "256", "-h", "ldap:///"]
```

## What good LLM output looks like

- `slapd.conf` with a global `disallow bind_anon` line.
- `slapd.conf` with `require authc` (or `strong` / `sasl`) on the
  database block.
- cn=config LDIF with `olcDisallows: bind_anon` on `cn=config`, or
  `olcRequires: authc` on the database entry.
- A `slapd` invocation that points `-F` at an external config directory
  the detector cannot inspect (we defer to the file-based rules).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/cn_config_ldif_acl_only.ldif
BAD  samples/bad/cn_config_ldif_no_disallow.ldif
BAD  samples/bad/dockerfile_slapd_no_disallow.Dockerfile
BAD  samples/bad/slapd_conf_no_disallow.conf
GOOD samples/good/cn_config_ldif_disallow.ldif
GOOD samples/good/dockerfile_slapd_with_F.Dockerfile
GOOD samples/good/slapd_conf_disallow_bind_anon.conf
GOOD samples/good/slapd_conf_require_authc.conf
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good
samples are flagged.

## Detector rules

A file is classified into exactly one of three modes; the first match
wins:

1. **Pure invocation** (`slapd` on the command line, no embedded
   directives). Flagged if it has no `-o disallow=bind_anon` AND no
   `-f` / `-F` pointing at an external config the detector cannot
   inspect.
2. **cn=config / OLC LDIF** (contains `dn: cn=config`, `olcDatabase`,
   `olcSuffix`, `olcRootDN`, or any `olc*:` attribute). Flagged if it
   has no `olcDisallows: bind_anon` AND no `olcRequires: authc`
   (`strong` / `sasl` also accepted).
3. **Legacy `slapd.conf`** (contains `database mdb|hdb|bdb|ldif|monitor`,
   `suffix "..."`, `rootdn "..."`, or `access to ...`). Flagged if it
   has no `disallow ... bind_anon` AND no `require ... authc` /
   `strong` / `sasl`.

`#` line comments are stripped before matching (both `slapd.conf` and
LDIF use `#` at column 0; `slapd.conf` also accepts inline `#`).

## Known false-positive notes

- Multi-file deployments that split `disallow bind_anon` into a separate
  `cn=config` LDIF imported at runtime will be flagged on the data
  LDIF in isolation. Suppress per-file via your repo's existing
  detector-suppression mechanism.
- `slapd` fronted by a SASL proxy that rewrites every bind to an
  authenticated identity does technically eliminate anonymous access,
  but the directory still serves the Root DSE to anonymous clients
  unless `disallow bind_anon` is also set — the detector's flag is
  consistent with OpenLDAP's own admin guide.
- `olcAccess` / `access to` rules alone do not satisfy the detector,
  by design: they restrict what an anonymous bind can *read*, not
  whether the bind succeeds.
