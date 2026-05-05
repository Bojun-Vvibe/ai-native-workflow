# llm-output-lighttpd-dir-listing-enable-detector

Static lint that flags `lighttpd` configurations enabling automatic
HTML directory listings. When asked "serve this folder over HTTP with
lighttpd", models routinely paste in:

```conf
server.modules += ( "mod_dirlisting" )
dir-listing.activate = "enable"
```

…or the legacy alias:

```conf
server.dir-listing = "enable"
```

…which makes lighttpd emit a directory index page for any URL that
maps to a filesystem directory without an `index.html`. The result
is information disclosure — backups, `.git/`, dotfiles, half-finished
docs, dump files — all become clickable links. Real deployments
either leave dir-listing off (the default) or enable it only inside
a narrow `$HTTP["url"] =~ "^/public/"` selector with sanitised
contents.

## Bad patterns this catches

A non-comment line, at top-level scope (i.e. NOT nested inside a
`$HTTP[...] { ... }` selector block), of the form:

- `dir-listing.activate = "enable"` (case-insensitive value)
- `dir-listing.activate = "1"` / `= 1`
- `server.dir-listing = "enable"` (legacy alias)
- `server.dir-listing = "1"` / `= 1`

Trailing comments (`# ...`) and surrounding whitespace are stripped
before evaluation. Lines whose value is `"disable"`, `"0"`, or `0`
are not flagged.

## Good patterns

- Default (no `dir-listing.activate` line at all).
- `dir-listing.activate = "disable"`.
- `dir-listing.activate = "enable"` placed *inside* a
  `$HTTP["url"] =~ "^/public/" { ... }` block (scoped enable).
- Any of the above tokens appearing only inside a `#`-comment.

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Exit 0 iff every bad sample is flagged AND no good sample is.
