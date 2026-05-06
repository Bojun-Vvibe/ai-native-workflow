# llm-output-jetty-realm-properties-default-credentials-detector

Detect Jetty `realm.properties` (HashLoginService) snippets that
LLMs commonly emit shipping the canonical demo credentials
(`admin: admin, server-administrator, …`) or other obvious
placeholder credentials. Jetty's `HashLoginService` loads this
file at startup; whoever knows a username + password in it gets
the listed roles, which on Solr / standalone Jetty installs
typically include `server-administrator` /
`content-administrator` / `admin` and grants full management
access to the embedded apps.

When asked "give me a Jetty realm.properties for my Solr / Jetty
container" or "set up basic auth on my Jetty admin webapp",
models routinely:

- Reproduce the demo file shipped with Jetty for decades
  (`admin: admin, server-administrator, content-administrator, admin`).
- Render `solr: changeme, admin` from old Solr install guides.
- Render `jetty: jetty, manager-gui, manager-script`.
- Render a short numeric / dictionary password on a line whose
  roles include `admin` / `server-administrator` /
  `manager-gui` / `manager-script`.

## Format

`realm.properties` lines follow Jetty's documented grammar:

```
username: password[,role1,role2,...]
```

The password may be plaintext, `OBF:...`, `MD5:...`, or
`CRYPT:...`. Jetty ships a `Password` utility that produces the
hashed forms. Plaintext is supported but discouraged.

## Bad patterns

1. A line `<user>: <user>[, ...roles]` — password equals the
   username (the demo file's shape: `admin: admin, ...`).
2. A line `<user>: <placeholder>[, ...roles]` for placeholder
   ∈ {`password`, `changeme`, `todo`, `xxx`, `placeholder`,
   `replaceme`, `secret`, `default`, `jetty`, `demo`, `test`,
   `123456`, `qwerty`, `letmein`, `root`, `pass`, `admin123`}.
3. A line `<user>: <plaintext-password>[, ...roles]` where one
   of the roles is an admin-shaped role
   (`admin`, `administrator`, `server-administrator`,
   `manager-gui`, `manager-script`, `content-administrator`,
   `manager`, `root`) AND the password is shorter than 8
   characters.

## Good patterns

- Hashed passwords (`OBF:`, `MD5:`, `CRYPT:` prefixes).
- Plaintext passwords ≥ 8 characters that are not placeholders
  and are not equal to the username.
- A `realm.properties`-shaped file where every credential line
  is commented out.
- A non-`realm.properties` file (JSON, YAML, INI section
  headers) that happens to contain `admin: admin` — the
  detector requires the canonical `username: password[,roles]`
  grammar without competing format markers.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Verified-runnable smoke output (verbatim):

```
BAD  samples/bad/01-admin-admin.conf
BAD  samples/bad/02-placeholder-pw.conf
BAD  samples/bad/03-short-admin-role.conf
BAD  samples/bad/04-jetty-jetty.conf
GOOD samples/good/01-all-hashed.conf
GOOD samples/good/02-strong-plaintext-non-admin.conf
GOOD samples/good/03-comments-only.conf
GOOD samples/good/04-not-realm-properties.conf
bad=4/4 good=0/4 PASS
```

## Why this matters

`HashLoginService` is the most common auth backend for Jetty
deployments embedded in other products (Solr ≤ 8.x ships it;
many vendor appliances use it). The `admin: admin` line is the
one shipped in the upstream demo and reproduced in countless
blog posts; LLMs have memorized it. On a Solr-on-Jetty install,
that one line grants every Solr admin endpoint (collection
create / delete, config push, replication) to anyone who can
reach the Jetty port. On a standalone Jetty serving
`manager-gui` / `manager-script`, it grants the ability to
deploy arbitrary WAR files — i.e. RCE.

The detector is deliberately narrow:

- Requires the canonical `username: password[,roles]` shape.
  Files that are JSON / YAML / INI sections do not fire.
- Hashed values (`OBF:`, `MD5:`, `CRYPT:`) are always treated
  as good — Jetty's `Password` utility produces them.
- Plaintext passwords are only flagged when (a) they equal the
  username, (b) they are a known placeholder, or (c) they are
  short AND the line carries an admin-shaped role.
- Plaintext passwords on non-admin roles (e.g. `monitor`,
  `viewer`) do not fire even if short — that's a weak-password
  smell, not the demo-credentials smell this detector is
  scoped to.

Bash 3.2+ / awk / coreutils only. No network calls.
