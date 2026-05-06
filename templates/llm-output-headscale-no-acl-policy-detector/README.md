# llm-output-headscale-no-acl-policy-detector

Detect Headscale (open-source Tailscale control plane) configurations
that LLMs routinely emit with no ACL policy wired in. Headscale's
default — when no policy file or DB policy is configured — is "all
nodes can reach all nodes on every port". Joining a single rogue
device to such a tailnet exposes every other node's full TCP/UDP
surface (SSH, RDP, internal HTTP admin panels, databases bound to the
tailnet interface, kubelet on `100.64.0.0/10`, etc.) without any
network-level mediation.

When asked "set me up a Headscale server" or "give me a
`config.yaml` for headscale", models routinely:

- Leave `policy.path` unset / empty / commented out.
- Set `policy.mode: file` but point `policy.path` at a non-existent
  or empty path (Headscale silently falls back to permit-all).
- Ship a `policy.path` whose target file is the well-known
  permit-everything example (`acls: [{ action: accept, src: ["*"],
  dst: ["*:*"] }]`).
- Ship `acl_policy_path:` (the legacy v0.22-and-earlier key) pointing
  at the same permit-all stub.

## Bad patterns

1. A YAML file that looks like a Headscale `config.yaml` (has a
   `server_url:` and either `listen_addr:` or `private_key_path:` or
   a `database:` / `db_type:` block) AND has no `policy.path`,
   `policy.mode + path`, or top-level `acl_policy_path:` set to a
   non-empty value.
2. A Headscale `config.yaml` whose `policy.path` / `acl_policy_path:`
   is the literal empty string `""`, `''`, or unquoted blank.
3. A Headscale ACL policy file (HuJSON / YAML with an `acls:` key)
   whose only rule is `action: accept` with `src: ["*"]` and
   `dst: ["*:*"]` (or `"*"`).
4. CLI invocation `headscale serve` / `headscale ... --config <f>`
   where the referenced config (passed inline via `--policy ""` or
   `--policy-mode database` with no DB policy loaded) disables the
   policy.

## Good patterns

- `config.yaml` with `policy.path: /etc/headscale/acl.hujson` AND a
  policy file that has at least one non-wildcard `src` or `dst`.
- `config.yaml` with `policy.mode: database` (operator manages
  policy through `headscale policy set`).
- ACL policy files with grouped/tagged ACLs (e.g. `src: ["group:eng"]`,
  `dst: ["tag:prod:22"]`).
- `config.yaml` files whose `policy.path` is commented out **and**
  there is no other Headscale-shaped key (i.e. the file is not a
  Headscale config at all).

## Tests

```sh
./detect.sh samples/bad/* samples/good/*
```

Expected: `bad=4/4 good=0/4 PASS`.

## Why this matters

Headscale is widely deployed by hobbyists and small teams as a
self-hosted Tailscale alternative. The upstream `config-example.yaml`
historically shipped with `policy.path: ""` commented near the bottom
of the file, and the README's "minimal config" snippet contains no
policy at all. LLMs that have been trained on these examples
faithfully reproduce them — producing a working tailnet that grants
mesh-wide lateral movement to any device that successfully registers.
