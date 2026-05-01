# llm-output-nginx-alias-traversal-detector

Stdlib-only Python detector that flags nginx config blocks combining a
`location` prefix **without** a trailing slash and an `alias` directive
**with** a trailing slash. This is the canonical CWE-22 path-traversal
misconfiguration: a request for `/static../etc/passwd` is rewritten to
`/var/www/static/../etc/passwd` and resolved upward, exposing arbitrary
files on the host filesystem.

## Why this anchor

Of all the unsafe shapes nginx allows, the `alias` slash mismatch is
the one LLMs reproduce most reliably. Many widely-cited blog snippets
do it, real-world exploitation is well documented (Acunetix and
Detectify both have classic write-ups), and the bug is invisible to
casual review because the two slashes "look fine" individually.

The bug requires:

1. A **prefix** location (not regex `~` / `~*`, not exact `=`, not
   `^~`) — only prefix matching exhibits the trailing-slash strip.
2. The location prefix has no trailing `/`.
3. The body uses `alias` (not `root` — `root` has different
   concatenation semantics and is not affected).
4. The `alias` value ends in `/`.

When all four hold, an attacker can append `../` segments to the
location prefix and escape the alias directory.

## Heuristic

For every `location` block in the file, check the four conditions
above. Lines beginning with `#` are stripped first (preserving
newlines so reported line numbers stay accurate). Brace matching is
balanced so nested `server { ... location { ... } }` blocks are
parsed correctly.

The detector does **not** flag:

- `location /static/ { alias /var/www/static/; }` — slashes match.
- `location /static { alias /var/www/static; }` — neither has a
  trailing slash.
- `location ~ ^/static/ { ... alias ... }` — regex location.
- `location /static { root /var/www; }` — `root` is safe here.
- Commented-out config (`# location /static { alias /...//; }`).

## CWE / standards

- **CWE-22**: Improper Limitation of a Pathname to a Restricted
  Directory ("Path Traversal").
- **CWE-23**: Relative Path Traversal.
- **OWASP A01:2021** — Broken Access Control.

## Limits / known false negatives

- Does not parse nginx includes (`include /etc/nginx/conf.d/*.conf`)
  — each file is scanned in isolation.
- Does not catch dynamic alias values built from variables
  (`alias $document_root/static/;`).
- Does not warn on the related `try_files` traversal pattern (that's
  a separate detector).

## Usage

```bash
python3 detect.py path/to/nginx.conf
python3 detect.py path/to/dir/   # walks *.conf, nginx.conf, *.conf.txt
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=4/4 good=0/5
PASS
```

Layout:

```
examples/bad/
  01_classic_static.conf         # location /static + alias /.../
  02_quoted_alias.conf           # quoted alias path with trailing /
  03_nested_with_comment.conf    # nested server{} with inline comment
  04_uploads.conf                # location /uploads + alias /.../
examples/good/
  01_matching_slashes.conf       # both ends with /
  02_neither_slash.conf          # neither ends with /
  03_regex_location.conf         # location ~ ^/static/
  04_root_not_alias.conf         # uses root, not alias
  05_commented_out.conf          # dangerous line is commented out
```
