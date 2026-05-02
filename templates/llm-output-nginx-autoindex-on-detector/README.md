# llm-output-nginx-autoindex-on-detector

Static lint that flags nginx config snippets that enable `autoindex on;`
inside a `server` / `location` / `http` block, exposing automatic
directory listings to anyone who can reach the location.

`autoindex on;` makes nginx render an HTML index of any directory under
the matched `location` that lacks an `index` file. LLM-generated nginx
configs frequently turn this on as a "quick way to share files" without
realizing it exposes the whole directory tree — including `.git`,
`.env`, backup tarballs, and stray `id_rsa` files — to the public
internet.

## What it catches

- `autoindex on;` at any block scope.
- Variants `autoindex_exact_size on;` / `autoindex_localtime on;` only
  when paired with an enabling `autoindex on;` in the same file (those
  alone are inert).
- Trailing-comment placements (`autoindex on; # FIXME`).
- Mixed-case / extra whitespace (`AutoIndex   on ;`).

## CWE references

- [CWE-548](https://cwe.mitre.org/data/definitions/548.html): Exposure
  of Information Through Directory Listing
- [CWE-538](https://cwe.mitre.org/data/definitions/538.html): Insertion
  of Sensitive Information into Externally-Accessible File or Directory
- [CWE-200](https://cwe.mitre.org/data/definitions/200.html): Exposure
  of Sensitive Information to an Unauthorized Actor

## False-positive surface

- Internal-only file-browser locations behind `allow` / `deny` ACLs or
  `auth_basic`. Suppress per file with `# nginx-autoindex-allowed`
  anywhere in the file.
- `autoindex off;` is fine and is the nginx default.
- Commented-out `autoindex on;` lines are ignored.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/4
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
