#!/usr/bin/env python3
r"""Detect AWS S3 bucket configurations that grant public access via SDK calls.

The terraform sibling detector covers IaC. This detector covers
*application code* using AWS SDKs (boto3, aws-sdk-js v2/v3, aws-sdk-go,
aws-sdk-java) to programmatically open buckets to the public.

Two canonical insecure shapes:

1. `PutBucketAcl` / `put_bucket_acl` / `putObjectAcl` with a canned
   ACL of `public-read`, `public-read-write`, or
   `authenticated-read`.
2. `PutBucketPolicy` / `put_bucket_policy` with a JSON body whose
   `Principal` is `"*"` or `{"AWS": "*"}` and whose `Effect` is
   `"Allow"` — i.e. the bucket policy itself opens the bucket
   to the world.

Why this matters
----------------

Public S3 buckets remain one of the top causes of real-world data
leaks. Static-site hosting and "share with a partner" snippets are
frequently lifted into production code unchanged, and `public-read`
is one keystroke away from `private` in every SDK.

What this flags
---------------

Python (`*.py`) — boto3:

* `put_bucket_acl(... ACL="public-read" | "public-read-write" |
  "authenticated-read" ...)` →
  `aws-s3-py-put-bucket-acl-public`.
* `put_object_acl(... ACL="public-read" | ...)` →
  `aws-s3-py-put-object-acl-public`.
* `create_bucket(... ACL="public-read" | ...)` →
  `aws-s3-py-create-bucket-acl-public`.
* `put_bucket_policy(...)` whose policy body contains
  `"Principal": "*"` or `"Principal": {"AWS": "*"}` with
  `"Effect": "Allow"` within 12 lines →
  `aws-s3-py-put-bucket-policy-wildcard-principal`.

Node (`*.js`, `*.ts`, `*.mjs`, `*.cjs`) — aws-sdk v2/v3:

* `PutBucketAclCommand({ ... ACL: 'public-read' | 'public-read-write'
  | 'authenticated-read' ... })` →
  `aws-s3-js-put-bucket-acl-public`.
* `s3.putBucketAcl({ ... ACL: 'public-...' ... })` (v2) →
  `aws-s3-js-put-bucket-acl-public`.
* `PutBucketPolicyCommand({ ... })` with wildcard principal in the
  same call → `aws-s3-js-put-bucket-policy-wildcard-principal`.

Go (`*.go`) — aws-sdk-go-v2 / -v1:

* `PutBucketAcl` / `PutBucketAclInput` with
  `ACL: "public-read" | ...` or `ACL: types.BucketCannedACLPublicRead`
  / `...PublicReadWrite` / `...AuthenticatedRead` →
  `aws-s3-go-put-bucket-acl-public`.

Java (`*.java`) — aws-sdk-java v1/v2:

* `setCannedACL(CannedAccessControlList.PublicRead | PublicReadWrite
  | AuthenticatedRead)` or `.acl(ObjectCannedACL.PUBLIC_READ | ...)`
  → `aws-s3-java-canned-acl-public`.

Cross-language JSON bucket policies (any source file):

* A line containing `"Principal"\s*:\s*"*"` (or `{"AWS": "*"}`)
  whose surrounding 6-line window also contains `"Effect": "Allow"`
  → `aws-s3-bucket-policy-wildcard-principal-allow`.

What this does NOT flag
-----------------------

* `put_bucket_acl(... ACL="private")` or any non-public canned ACL.
* Bucket policies whose `Effect` is `"Deny"` even with wildcard
  principal (these are *deny-all-but* policies, which are safe by
  design).
* Lines marked with a trailing `# s3-public-ok` or `// s3-public-ok`
  comment.
* Patterns inside `#` or `//` comment lines.
* Files under any path segment named `test`, `tests`, `_test`,
  `__tests__`, `testdata`, or with a name ending `_test.go` /
  `.test.js` / `.test.ts`.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 on findings, 0 otherwise. python3 stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".json"}

RE_SUPPRESS = re.compile(r"(?:#|//)\s*s3-public-ok\b")
RE_PY_COMMENT = re.compile(r"^\s*#")
RE_SLASH_COMMENT = re.compile(r"^\s*//")

PUBLIC_CANNED = ("public-read-write", "public-read", "authenticated-read")

# Python boto3
RE_PY_PUT_BUCKET_ACL = re.compile(r"\.put_bucket_acl\s*\(")
RE_PY_PUT_OBJECT_ACL = re.compile(r"\.put_object_acl\s*\(")
RE_PY_CREATE_BUCKET = re.compile(r"\.create_bucket\s*\(")
RE_PY_PUT_BUCKET_POLICY = re.compile(r"\.put_bucket_policy\s*\(")
RE_PY_ACL_KW = re.compile(r"""ACL\s*=\s*['"]([a-zA-Z\-]+)['"]""")

# Node
RE_JS_PUT_BUCKET_ACL_CMD = re.compile(r"\b(?:new\s+)?PutBucketAclCommand\s*\(")
RE_JS_PUT_BUCKET_ACL_V2 = re.compile(r"\.putBucketAcl\s*\(")
RE_JS_PUT_BUCKET_POLICY_CMD = re.compile(r"\b(?:new\s+)?PutBucketPolicyCommand\s*\(")
RE_JS_PUT_BUCKET_POLICY_V2 = re.compile(r"\.putBucketPolicy\s*\(")
RE_JS_ACL_KEY = re.compile(r"""ACL\s*:\s*['"]([a-zA-Z\-]+)['"]""")

# Go
RE_GO_ACL_FIELD = re.compile(r"""\bACL\s*:\s*['"]?([a-zA-Z\-_.]+)['"]?""")
RE_GO_PUT_BUCKET_ACL = re.compile(r"\bPutBucketAcl(?:Input)?\b")
GO_PUBLIC_ENUMS = (
    "BucketCannedACLPublicRead",
    "BucketCannedACLPublicReadWrite",
    "BucketCannedACLAuthenticatedRead",
    "ObjectCannedACLPublicRead",
    "ObjectCannedACLPublicReadWrite",
    "ObjectCannedACLAuthenticatedRead",
)

# Java
RE_JAVA_CANNED = re.compile(
    r"\b(?:CannedAccessControlList|ObjectCannedACL|BucketCannedACL)\s*\.\s*(PublicRead|PublicReadWrite|AuthenticatedRead|PUBLIC_READ|PUBLIC_READ_WRITE|AUTHENTICATED_READ)\b"
)

# Wildcard principal (cross-language JSON-ish; supports unquoted JS keys)
RE_PRINCIPAL_WILDCARD = re.compile(
    r"""['"]?Principal['"]?\s*:\s*(?:['"]\*['"]|\{\s*['"]?AWS['"]?\s*:\s*['"]\*['"]\s*\})"""
)
RE_EFFECT_ALLOW = re.compile(r"""['"]?Effect['"]?\s*:\s*['"]Allow['"]""")

TEST_PATH_PARTS = {"test", "tests", "_test", "__tests__", "testdata"}


def is_test_path(p: Path) -> bool:
    parts = {part.lower() for part in p.parts}
    if parts & TEST_PATH_PARTS:
        return True
    name = p.name.lower()
    if name.endswith("_test.go"):
        return True
    if name.endswith(".test.js") or name.endswith(".test.ts"):
        return True
    return False


def is_comment_line(line: str, suffix: str) -> bool:
    if suffix == ".py":
        return bool(RE_PY_COMMENT.match(line))
    if suffix == ".json":
        return False
    return bool(RE_SLASH_COMMENT.match(line))


def collect_call_block(lines, idx, max_lines=12):
    """Concat the next `max_lines` lines for crude block-level kw scanning."""
    return "\n".join(lines[idx : idx + max_lines])


def has_wildcard_allow_pair(lines, start_idx, end_idx):
    """Return True iff the [start, end) window contains a wildcard
    principal whose closest Effect (within 3 lines either side) is
    "Allow". Avoids false positives where the same call also defines
    a Deny statement nearby with its own wildcard principal."""
    end_idx = min(end_idx, len(lines))
    for k in range(max(0, start_idx), end_idx):
        if RE_PRINCIPAL_WILDCARD.search(lines[k]):
            local = "\n".join(lines[max(0, k - 3) : k + 4])
            if RE_EFFECT_ALLOW.search(local):
                return True
    return False


def scan_file(path: Path):
    findings = []
    if path.suffix not in SUFFIXES:
        return findings
    if is_test_path(path):
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    lines = text.splitlines()
    suffix = path.suffix

    for i, line in enumerate(lines):
        if RE_SUPPRESS.search(line):
            continue
        if is_comment_line(line, suffix):
            continue
        ln = i + 1

        # Cross-language: wildcard principal + allow within 3 lines (same statement)
        if RE_PRINCIPAL_WILDCARD.search(line):
            window = "\n".join(lines[max(0, i - 3) : i + 4])
            if RE_EFFECT_ALLOW.search(window):
                findings.append(
                    (path, ln, "aws-s3-bucket-policy-wildcard-principal-allow", line.strip())
                )

        if suffix == ".py":
            if RE_PY_PUT_BUCKET_ACL.search(line):
                block = collect_call_block(lines, i)
                m = RE_PY_ACL_KW.search(block)
                if m and m.group(1).lower() in PUBLIC_CANNED:
                    findings.append((path, ln, "aws-s3-py-put-bucket-acl-public", line.strip()))
            if RE_PY_PUT_OBJECT_ACL.search(line):
                block = collect_call_block(lines, i)
                m = RE_PY_ACL_KW.search(block)
                if m and m.group(1).lower() in PUBLIC_CANNED:
                    findings.append((path, ln, "aws-s3-py-put-object-acl-public", line.strip()))
            if RE_PY_CREATE_BUCKET.search(line):
                block = collect_call_block(lines, i)
                m = RE_PY_ACL_KW.search(block)
                if m and m.group(1).lower() in PUBLIC_CANNED:
                    findings.append((path, ln, "aws-s3-py-create-bucket-acl-public", line.strip()))
            if RE_PY_PUT_BUCKET_POLICY.search(line):
                if has_wildcard_allow_pair(lines, i - 20, i + 20):
                    findings.append(
                        (path, ln, "aws-s3-py-put-bucket-policy-wildcard-principal", line.strip())
                    )

        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            if RE_JS_PUT_BUCKET_ACL_CMD.search(line) or RE_JS_PUT_BUCKET_ACL_V2.search(line):
                block = collect_call_block(lines, i)
                m = RE_JS_ACL_KEY.search(block)
                if m and m.group(1).lower() in PUBLIC_CANNED:
                    findings.append((path, ln, "aws-s3-js-put-bucket-acl-public", line.strip()))
            if RE_JS_PUT_BUCKET_POLICY_CMD.search(line) or RE_JS_PUT_BUCKET_POLICY_V2.search(line):
                if has_wildcard_allow_pair(lines, i - 20, i + 20):
                    findings.append(
                        (path, ln, "aws-s3-js-put-bucket-policy-wildcard-principal", line.strip())
                    )

        elif suffix == ".go":
            m = RE_GO_ACL_FIELD.search(line)
            if m:
                v = m.group(1)
                if v.lower() in PUBLIC_CANNED or v in GO_PUBLIC_ENUMS or any(
                    v.endswith(e) for e in GO_PUBLIC_ENUMS
                ):
                    findings.append((path, ln, "aws-s3-go-put-bucket-acl-public", line.strip()))

        elif suffix == ".java":
            if RE_JAVA_CANNED.search(line):
                findings.append((path, ln, "aws-s3-java-canned-acl-public", line.strip()))

    return findings


def iter_files(targets):
    for t in targets:
        p = Path(t)
        if p.is_file():
            yield p
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file():
                    yield sub


def main(argv):
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    findings = []
    for f in iter_files(argv[1:]):
        findings.extend(scan_file(f))
    for path, ln, code, snippet in findings:
        print(f"{path}:{ln}: {code}: {snippet}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
