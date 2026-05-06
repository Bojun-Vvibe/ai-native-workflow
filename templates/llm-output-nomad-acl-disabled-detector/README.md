# llm-output-nomad-acl-disabled-detector

Detect HashiCorp Nomad agent configurations (HCL or JSON) that LLMs
routinely emit with the ACL system disabled or simply omitted. Nomad
ACLs gate every API endpoint — job submission, namespace access,
node drain, even the read-only UI. When the `acl` block is absent
or has `enabled = false`, the entire cluster is open: any client on
the network can submit jobs that run as root on every node.

When asked "give me a Nomad server config" / "set up a Nomad
cluster" / "Nomad docker-compose", models routinely:

- Emit `server { enabled = true ... }` and `client { enabled = true }`
  blocks but **never** add an `acl` block.
- Emit `acl { enabled = false }` because they copy from a tutorial
  that explicitly turns ACLs off "for the demo".
- Set `ACL_ENABLED=false` (or omit it) in env-driven configs for
  the `hashicorp/nomad` image.

## Bad patterns (any one is sufficient on a snippet that *is* a
Nomad agent config — see scope)

1. HCL: an `acl { ... }` block whose `enabled` key is `false`
   (or `0`, `"false"`).
2. HCL: a server or client config (`server { enabled = true }` /
   `client { enabled = true }`) with **no** `acl` block at all.
3. JSON: top-level `"acl": { "enabled": false }`.
4. JSON: a server/client agent config with no `acl` key.
5. Env-driven: `NOMAD_*` env vars present (or `hashicorp/nomad`
   image with a CLI command starting `agent -server` / `agent -client`)
   without `NOMAD_ACL_ENABLED=true` and without an HCL/JSON config
   that enables ACLs in the same snippet.

## Good patterns

- HCL: `acl { enabled = true }` co-located with the server/client
  block(s).
- JSON: `"acl": { "enabled": true }`.
- Env: `NOMAD_ACL_ENABLED=true` plus the agent command.
- Snippets that don't actually configure a Nomad agent
  (out of scope, not flagged).

## Scope fingerprint

We only inspect a snippet if it looks like a Nomad agent config:

- An HCL `server {` or `client {` block with `enabled = true`, OR
- A JSON `"server"` or `"client"` object with `"enabled": true`, OR
- A `hashicorp/nomad` image reference with a `nomad agent` command, OR
- Any `NOMAD_*` env var (excluding `NOMAD_ADDR` alone, which is
  client-side and unrelated).

This avoids flagging Consul / Vault / unrelated HCL.

## False-positive notes

- A snippet that is purely a Nomad **client of an external server**
  (i.e., `nomadclient { servers = [...] }` only, no `enabled`
  block) is out of scope — ACL enforcement happens at the server.
- We do not parse HCL structurally; we scan for the canonical
  `acl { ... enabled = ... }` shape and the `client`/`server`
  block headers. A `# acl { enabled = true }` comment line does
  not count (we strip `#` and `//` comments first).
- `acl = { enabled = true }` (HCL2 attribute syntax) is also
  accepted as good.
