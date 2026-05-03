# llm-output-zeppelin-anonymous-shiro-auth-detector

Stdlib-only Python detector that flags **Apache Zeppelin** Shiro
configurations that leave the notebook UI unauthenticated by mapping
the catch-all URL pattern to the `anon` filter.

Maps to **CWE-306** (Missing Authentication for Critical Function),
**CWE-284** (Improper Access Control), and **CWE-1188** (Insecure
Default Initialization of Resource).

Zeppelin notebooks routinely embed credentials, run shell / Spark /
JDBC interpreters, and expose result sets that include PII. An
unauthenticated UI on port 8080 is, in practice, remote code
execution as the Zeppelin service account.

The relevant Shiro INI surface is `[urls]`. The *last* filter in a
chain decides allow/deny. The default tutorial line that LLMs love
to reproduce is:

```
[urls]
/** = anon
```

…which assigns the **anonymous** filter to every URL under the web
app, bypassing any LDAP / PAM / form realm configured above it.
The fix is `/** = authc`.

## Heuristic

Inside the `[urls]` section of a Shiro INI (or any INI-shaped file
that contains a `[urls]` header), we flag any line that:

1. Maps a catch-all path (`/**`, `/*`, `/api/**`, `/api/*`) to a
   chain whose **final** filter is `anon`.
2. Maps a catch-all path to an empty chain `=` (Shiro treats this
   as anon).

We also flag the bare textual pattern `/** = anon` outside any
section, because LLMs sometimes paste the snippet without the
section header.

We do NOT flag:

- `/login = anon` or `/api/version = anon` (intentionally public
  endpoints); the path must be a catch-all.
- Lines inside `#` / `;` comments (those are warnings, not config).
- A chain that lists `anon` mid-chain but ends in `authc`.

## What we flag

- `/** = anon`
- `/api/** = anon`
- `/** =`            (empty chain, Shiro treats as anon)
- bare snippet `/** = anon` pasted into install notes / READMEs.

## What we accept

- `/** = authc`
- `/api/notebook/** = anon, authc`  (final filter wins)
- `/login = anon`
- Comment-only mentions: `# DO NOT use /** = anon`.

## CWE / standards

- **CWE-306**: Missing Authentication for Critical Function.
- **CWE-284**: Improper Access Control.
- **CWE-1188**: Insecure Default Initialization of Resource.
- Apache Zeppelin security docs: "Zeppelin uses Apache Shiro for
  authentication and resource management. The default
  configuration is for development and is **not secure**."

## Usage

```bash
python3 detect.py path/to/conf/shiro.ini
python3 detect.py path/to/repo/
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/3
PASS
```

Layout:

```
examples/bad/
  01_classic_anon_catchall.ini       # /** = anon overrides LDAP realm
  02_api_catchall_anon.ini           # /api/** = anon
  03_empty_chain.ini                 # /** =       (empty chain)
  04_bare_snippet_in_notes.properties # bare /** = anon paste
examples/good/
  01_authc_catchall.ini              # /** = authc with role pin
  02_anon_midchain_authc_final.ini   # anon, authc -- final wins
  03_warning_in_comments_only.properties # only mentions in comments
```

## Limits / known false negatives

- We assume Shiro INI syntax. Programmatic Shiro configuration
  (Java `IniSecurityManagerFactory`) that builds the chain at
  runtime is out of scope.
- We do not parse `roles[...]` or `perms[...]` arguments; we only
  inspect the *name* of the final filter.
- Sibling detectors in this series cover Zeppelin's
  `zeppelin.anonymous.allowed=true` and `shiro.ini` missing
  entirely; this detector covers the explicit anon mapping.
