# llm-output-terraform-security-group-open-detector

**CWE:** [CWE-732 — Incorrect Permission Assignment for Critical Resource](https://cwe.mitre.org/data/definitions/732.html) / [CWE-284 — Improper Access Control](https://cwe.mitre.org/data/definitions/284.html)
**Language:** Terraform HCL (AWS provider)
**Static analysis only.** Defensive linter for LLM-generated infra.

## What it catches

LLMs writing AWS Terraform routinely emit "open to the world" security
group ingress rules — usually to make a copy-pasted module work in the
demo, then never tightened. The shortest-path emission is:

```hcl
resource "aws_security_group" "db" {
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

That happily exposes the database to the entire IPv4 internet. The
same pattern recurs for SSH (22), RDP (3389), Kubernetes API (6443),
Redis (6379), Elasticsearch (9200), Mongo (27017), Docker daemon
(2375/2376), SMB (445), MSSQL (1433), Oracle (1521), NFS (2049),
Salt master (4505/4506), etc.

This detector flags any AWS security group ingress that **both**:

1. opens to `0.0.0.0/0` or `::/0`; **and**
2. covers at least one port from the curated sensitive-port list
   (admin / database / clustering / message-broker ports), **or**
   covers the full 0–65535 range.

Three resource forms are recognised:

* nested `ingress { ... }` blocks inside `resource "aws_security_group"`;
* standalone `resource "aws_security_group_rule"` with `type = "ingress"`;
* the newer `resource "aws_vpc_security_group_ingress_rule"` (single
  `cidr_ipv4` / `cidr_ipv6` string field).

Common public-web ports (80, 443, 8080) are intentionally **not** in
the sensitive set — flagging them produces too much noise on real
codebases.

## What suppresses a finding

Per-block: append `# sg-open-ok` on the `ingress` / resource header
line.

Per-file (interop with existing tooling): include either of these
markers anywhere in the file:

```
# tfsec:ignore:sg-open
# checkov:skip=sg-open
```

Restricted CIDRs (`10.0.0.0/8`, `172.16.0.0/12`, a VPC CIDR
variable, etc.) and egress rules are never flagged.

## Usage

```bash
python3 detect.py path/to/terraform
python3 detect.py main.tf network.tf
```

Exit `1` if any findings, `0` otherwise. Pure stdlib Python 3.

## Worked example

```bash
./verify.sh
# bad findings:  7 (rc=1)
# good findings: 0 (rc=0)
# PASS
```

`examples/bad/` covers all three resource shapes plus the
fully-open-port-range case. `examples/good/` covers private CIDRs,
public web ports (80/443), per-block `# sg-open-ok`, and the
tfsec/checkov interop markers.

## Limits

- Heredoc / variable-interpolated CIDR lists are matched only when the
  literal `0.0.0.0/0` or `::/0` substring appears textually. A CIDR
  pulled exclusively from `var.public_cidr` will not fire.
- The from_port / to_port heuristic assumes integer literals. A range
  defined entirely via variables (`from_port = var.ssh_port`) is not
  evaluated.
- HCL JSON (`.tf.json`) files are skipped — production Terraform almost
  never uses that form.
- The detector does not understand `dynamic "ingress"` blocks; if your
  module generates ingress at apply-time, prefer `tfsec` / `checkov`
  for that path and use this detector as a pre-commit fast-fail.
