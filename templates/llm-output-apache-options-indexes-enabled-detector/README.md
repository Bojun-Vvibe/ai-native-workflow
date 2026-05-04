# llm-output-apache-options-indexes-enabled-detector

Detects Apache HTTPD configurations (`httpd.conf`, `apache2.conf`,
files under `conf.d/`, `sites-enabled/`, `mods-enabled/`, and
`.htaccess`) that turn on the `Indexes` option, which causes Apache
to render an HTML directory listing whenever a request hits a
directory with no `DirectoryIndex` match.

## Why this matters

`Options Indexes` (or `Options +Indexes`, or the catch-all
`Options All`) exposes:

- File names the operator never intended to publish (`.bak`,
  `.swp`, `.git/` artefacts, `backup.sql.gz`, build outputs,
  unfinished drafts).
- The directory tree shape, which accelerates targeted
  enumeration by attackers and crawlers.
- Source-control metadata, environment dumps, and stale upload
  forms that have not yet been cleaned up.

This is a long-standing OWASP "Sensitive Information Disclosure
through Directory Listing" finding (CWE-548). Despite Apache's own
`autoindex` README warning, LLM-generated configs frequently emit
shapes like:

```apache
<Directory "/var/www/html">
    Options Indexes FollowSymLinks
    AllowOverride None
    Require all granted
</Directory>
```

```apache
<Directory /srv/uploads>
    Options +Indexes
</Directory>
```

```apache
<Directory /var/www>
    Options All
</Directory>
```

…all of which enable indexes.

## What's checked

For each file, the detector parses every `Options` directive
(case-insensitive, anywhere in the file — top-level or nested
inside `<Directory>`, `<Location>`, `<Files>`, `<VirtualHost>`,
or `<IfModule>` blocks) and flags the file when it finds:

1. `Options Indexes` (bare or comma/space-separated with other
   tokens), OR
2. `Options +Indexes` (additive form), OR
3. `Options All` (which includes `Indexes`),

UNLESS the same directive contains `-Indexes` *after* the
enabling token (Apache evaluates left-to-right — but for safety
we treat any `-Indexes` on the same directive as a deliberate
removal).

`Options None` and `Options FollowSymLinks` (or any subset that
does not include `Indexes` / `All`) are not flagged.

## Accepted (not flagged)

- `Options None`, `Options FollowSymLinks`, `Options
  -Indexes`, `Options ExecCGI`, etc.
- Files containing the comment `# apache-indexes-allowed`
  (intentional public file-share fixtures).
- Files that have no `Options` directive at all.

## Refs

- CWE-548: Exposure of Information Through Directory Listing
- OWASP A05:2021 Security Misconfiguration

## Usage

```
python3 detector.py path/to/httpd.conf [more.conf ...]
```

Exit code = number of flagged files (capped at 255). Findings
print as `<file>:<line>:<reason>`.
