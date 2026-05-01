# llm-output-aws-iam-policy-wildcard-action-detector

Static lint that flags AWS IAM policy documents granting overly broad
permissions via wildcard `Action` (or `NotAction`) on an `Allow`
statement.

LLM-generated IAM policy JSON routinely produces statements like:

```json
{
  "Effect": "Allow",
  "Action": "*",
  "Resource": "*"
}
```

or the slightly more subtle:

```json
{
  "Effect": "Allow",
  "Action": ["s3:*", "iam:*"],
  "Resource": "*"
}
```

Both are textbook over-privilege. The first is the AWS-managed
`AdministratorAccess` shape and should never appear in a hand-written
inline policy attached to a workload role. The second still grants full
control over an entire service.

## What it catches

- `Effect: Allow` + `Action: "*"` + wildcard / absent `Resource`
- `Effect: Allow` + `Action: ["service:*", ...]` + wildcard `Resource`
- `Effect: Allow` + `NotAction: [...]` (allow-everything-except shape)
- `Effect: Allow` + `Action: "iam:*" / "sts:*" / "kms:*" /
  "organizations:*" / "account:*"` even when `Resource` is scoped
  (the blast radius of these privileged services is too high to ignore)

## CWE references

- [CWE-269](https://cwe.mitre.org/data/definitions/269.html): Improper
  Privilege Management
- [CWE-732](https://cwe.mitre.org/data/definitions/732.html): Incorrect
  Permission Assignment for Critical Resource
- [CWE-285](https://cwe.mitre.org/data/definitions/285.html): Improper
  Authorization

## False-positive surface

- Trust policies (`sts:AssumeRole`) and break-glass admin roles
  legitimately need broad permissions. Suppress per file with a
  top-level `"_iam_wildcard_allowed": true` sibling of `Version`, or
  per statement with a `Sid` ending in `-AdminAllowed`.
- `Effect: Deny` statements with wildcards are safe and ignored.
- Non-policy JSON (no `Version` + `Statement` shape) is skipped.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at least
  one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
