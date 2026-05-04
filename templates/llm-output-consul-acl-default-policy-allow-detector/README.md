# llm-output-consul-acl-default-policy-allow-detector

Stdlib-only Python detector that flags HashiCorp Consul agent
configs setting `acl.default_policy = "allow"` (HCL),
`"acl": { "default_policy": "allow" }` (JSON / YAML), or the
CLI flag `-default-policy=allow`. Maps to **CWE-284**,
**CWE-732**, **CWE-1188**, OWASP **A01:2021 Broken Access Control**.

## What it catches

Consul's ACL system uses default-deny when
`default_policy = "deny"`: any token without an explicit policy
gets nothing. Flipping it to `"allow"` makes the **anonymous**
token a superuser: any unauthenticated request gets full
read/write access to KV, services, sessions, prepared queries,
and intentions. This is strictly worse than disabling ACLs
entirely, because operators believe they have access control
when they do not.

The Consul "getting started with ACLs" tutorial sets
`default_policy = "allow"` for the bootstrap migration step.
Many blog posts forget to flip it back to `"deny"`. LLMs
reproduce the bootstrap snippet as if it were the recommended
steady-state config.

## Heuristic

Flag any of:

- HCL: `default_policy = "allow"` inside an `acl { ... }` block
- HCL: legacy top-level `acl_default_policy = "allow"`
- JSON: `"default_policy": "allow"` inside `"acl": { ... }`
- YAML: `default_policy: allow` under an `acl:` parent (by indent)
- CLI / systemd: `consul agent ... -default-policy=allow` (or
  with a space separator)

Comments (`#`, `//`, `/* */`, and `;` for ini-ish files) are
stripped before matching, so commented-out snippets are ignored.

`default_policy = "deny"` is never flagged. A `default_policy =
"allow"` value that is **not** under an `acl` parent (e.g.
inside an unrelated nested block) is also not flagged.

## Worked example

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```

## Layout

```
examples/bad/
  01_hcl_acl_block.hcl              # acl { default_policy = "allow" }
  02_json_nested.json               # "acl": { "default_policy": "allow" }
  03_cli_flag.service               # ExecStart=consul agent -default-policy=allow
  04_legacy_top_level.hcl           # acl_default_policy = "allow"
examples/good/
  01_hcl_deny.hcl                   # acl { default_policy = "deny" }
  02_json_deny.json                 # "acl": { "default_policy": "deny" }
  03_commented_out.hcl              # bad value only inside `# ...` comments
  04_unrelated_block.hcl            # default_policy = "allow" under non-acl parent
```

## Usage

```bash
python3 detect.py path/to/consul.hcl
python3 detect.py path/to/repo/
```

Exit codes: `0` = clean, `1` = findings (printed to stdout), `2` =
usage error.

## Limits

- Templated configs (Consul-template, Helm, Sprig, Jinja) are
  not rendered.
- Environment-variable indirection
  (`CONSUL_ACL_DEFAULT_POLICY=allow`) is not chased.
- The YAML parent check is indentation-based; deeply nested
  YAML where the `acl:` ancestor uses non-standard indentation
  may produce false negatives.
