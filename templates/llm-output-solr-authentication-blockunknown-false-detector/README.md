# llm-output-solr-authentication-blockunknown-false-detector

Detect Apache Solr `security.json` files that LLMs commonly emit which
configure the `BasicAuthPlugin` (or the related `JWTAuthPlugin`)
**but** set `"blockUnknown": false`. That single boolean is Solr's
authentication kill-switch: when it is `false`, Solr accepts every
unauthenticated request as an anonymous user and only checks the
configured authentication plugin for *requests that already carry
credentials*. Combined with a permissive `authorization` block (or
the typical "let admins do everything, leave anonymous unrestricted"
shape that LLMs gravitate toward), every collection, every config
API, and every replication handler becomes reachable without a
password.

The Solr reference guide (`solr-tutorial.html#authentication`) and
multiple historical advisories (e.g., the 2019 `RunExecutableListener`
RCE chain, CVE-2017-12629) call this out: `blockUnknown` defaults to
`false` in Solr's own example `security.json`, which means a copy-
pasted starter file is unauthenticated by default. LLMs reproduce
that example faithfully and then add user/role tables on top, leaving
the "anyone can read" door wide open.

The hardening knob that closes this off is exactly one line:

```json
"authentication": {
  "blockUnknown": true,
  "class": "solr.BasicAuthPlugin",
  "credentials": { "...": "..." }
}
```

When asked "set up Solr authentication" or "give me a `security.json`
with admin/reader users", LLMs routinely paste either the upstream
example verbatim (which has `"blockUnknown": false`) or omit the key
entirely, which Solr also treats as `false`.

This detector is orthogonal to every other Solr-flavored detector in
the repo (none target `security.json`'s authentication block) and
to the broader "auth disabled" family — those target init flags or
config files; this one targets a single boolean inside a JSON
authentication plugin block.

Related weaknesses: CWE-287 (Improper Authentication), CWE-306
(Missing Authentication for Critical Function), CWE-1188 (Insecure
Default Initialization of Resource).

## What bad LLM output looks like

The canonical upstream example, reproduced verbatim:

```json
{
  "authentication": {
    "blockUnknown": false,
    "class": "solr.BasicAuthPlugin",
    "credentials": { "solr": "IV0EHq1OnNrj6gvRCwvFwTrZ1+z..." }
  }
}
```

Block-key style (different whitespace, same effect):

```json
{
  "authentication" : {
    "class"         : "solr.BasicAuthPlugin",
    "blockUnknown"  : false,
    "credentials"   : { "admin": "..." }
  }
}
```

JWT plugin variant (same kill-switch applies):

```json
{
  "authentication": {
    "class": "solr.JWTAuthPlugin",
    "blockUnknown": false,
    "jwk": { "...": "..." }
  }
}
```

## What good LLM output looks like

- `"blockUnknown": true` is set inside the `authentication` block.
- The file omits the `authentication` block entirely (no plugin
  configured at all is out of scope for this detector — pair with a
  separate "Solr no-auth" detector).
- The `blockUnknown` key appears with value `true` regardless of
  surrounding whitespace.

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/security_basic_auth_blockunknown_false.json
BAD  samples/bad/security_basic_auth_no_blockunknown.json
BAD  samples/bad/security_jwt_blockunknown_false.json
BAD  samples/bad/security_upstream_example_verbatim.json
GOOD samples/good/security_basic_auth_blockunknown_true.json
GOOD samples/good/security_jwt_blockunknown_true.json
GOOD samples/good/security_no_authentication_block.json
GOOD samples/good/security_blockunknown_true_compact.json
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero
good samples are flagged.

## Detector rules

A file is flagged iff the JSON contains an `authentication` block
whose `class` mentions a Solr authentication plugin AND one of the
following is true:

1. **`"blockUnknown"` is explicitly set to `false`** anywhere inside
   the `authentication` block (any whitespace around `:` and `,`).
2. **`"blockUnknown"` is absent from the `authentication` block** —
   Solr defaults to `false` in this case, which is the same outcome.

The detector is line-oriented and does not perform full JSON parsing;
it locates the `authentication` block by the appearance of one of
`"class": "solr.BasicAuthPlugin"`, `"class": "solr.JWTAuthPlugin"`,
or `"class": "solr.PKIAuthenticationPlugin"` and then checks the
five lines on either side for a `blockUnknown` setting. This
heuristic matches every shape the upstream Solr docs and starter
templates emit; it does not attempt to handle authentication blocks
spread across more than 11 lines.

## Known false-positive notes

- A file that mentions `solr.BasicAuthPlugin` only inside a
  documentation comment block (e.g., a `// ...` C-style comment in a
  `security.json5` variant) will still be inspected; Solr does not
  accept JSON5, so this is not a real-world configuration and we
  prefer the false positive over missing real footguns.
- A file that uses a non-Solr authentication plugin class (e.g., a
  custom `com.example.MyAuthPlugin`) is not flagged; the detector
  only knows about the three upstream plugins. Pair this detector
  with a code review of any custom plugin.
- A `blockUnknown` key that appears outside the `authentication`
  block (unusual but legal in malformed JSON) is ignored; only the
  five-line window on either side of the plugin `class` line is
  checked.
