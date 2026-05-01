# llm-output-aws-s3-bucket-public-acl-detector

Single-pass python3 stdlib scanner for AWS S3 bucket configurations
that grant public access via SDK calls. Sibling to the existing
`llm-output-terraform-aws-s3-public-acl-detector`, but scoped to
*application code* (boto3, aws-sdk-js v2/v3, aws-sdk-go v1/v2,
aws-sdk-java v1/v2) rather than IaC.

## Why it exists

Public S3 buckets remain one of the top causes of real-world data
leaks. LLM-emitted snippets routinely fall into this trap because:

- Static-site hosting and "share with a partner" examples are
  copy-pasted from quickstarts unchanged.
- `public-read` is one keystroke away from `private` in every SDK.
- Bucket policies with wildcard principals look "normal" in
  copy-pasted JSON because the JSON is structurally valid and
  IAM error messages are not produced at apply time.
- `Principal: "*"` with `Effect: "Allow"` is the canonical "share
  with everyone" pattern; LLMs reach for it whenever the user says
  "make it public" without thinking through scope.

This detector targets the exact SDK call shapes — not Terraform,
not CloudFormation, not the AWS console.

## What it flags

Python (`*.py`) — boto3:

- `put_bucket_acl(... ACL="public-read" | "public-read-write" |
  "authenticated-read" ...)` → `aws-s3-py-put-bucket-acl-public`.
- `put_object_acl(... ACL="public-..." ...)` →
  `aws-s3-py-put-object-acl-public`.
- `create_bucket(... ACL="public-..." ...)` →
  `aws-s3-py-create-bucket-acl-public`.
- `put_bucket_policy(...)` whose nearby JSON contains a wildcard
  principal whose closest `Effect` is `Allow` →
  `aws-s3-py-put-bucket-policy-wildcard-principal`.

Node (`*.js`, `*.ts`, `*.mjs`, `*.cjs`) — aws-sdk v2 / v3:

- `PutBucketAclCommand({ ... ACL: 'public-...' ... })` and
  `s3.putBucketAcl({ ... ACL: 'public-...' ... })` →
  `aws-s3-js-put-bucket-acl-public`.
- `PutBucketPolicyCommand({...})` / `s3.putBucketPolicy({...})` with
  wildcard principal in the surrounding statement →
  `aws-s3-js-put-bucket-policy-wildcard-principal`.

Go (`*.go`) — aws-sdk-go v1 / v2:

- `PutBucketAcl` / `PutBucketAclInput` with a public canned ACL
  string or `types.BucketCannedACLPublicRead` /
  `...PublicReadWrite` / `...AuthenticatedRead` →
  `aws-s3-go-put-bucket-acl-public`.

Java (`*.java`) — aws-sdk-java v1 / v2:

- Any reference to `CannedAccessControlList.PublicRead` /
  `PublicReadWrite` / `AuthenticatedRead` (and the v2 enum
  equivalents `ObjectCannedACL.PUBLIC_READ` etc.) →
  `aws-s3-java-canned-acl-public`.

Cross-language (any source file in scope):

- A line containing `Principal: "*"` (or `{"AWS": "*"}`) whose
  immediate ±3-line neighborhood also contains `Effect: "Allow"`
  → `aws-s3-bucket-policy-wildcard-principal-allow`.
  Quoted and unquoted JS/TS object-literal keys are both
  recognized.

## What it does NOT flag

- `put_bucket_acl(... ACL="private" | "bucket-owner-full-control")`
  and any other non-public canned ACL.
- Bucket policies whose `Effect` is `"Deny"` even with a wildcard
  principal — these are *deny-all-but* policies, which are safe by
  design (e.g. "deny non-TLS access").
- Lines marked with a trailing `# s3-public-ok` or
  `// s3-public-ok` comment.
- Patterns inside `#` or `//` comment lines.
- Files under any path segment named `test`, `tests`, `_test`,
  `__tests__`, `testdata`, or with a name ending in `_test.go`,
  `.test.js`, `.test.ts`.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on findings, `0` otherwise. python3 stdlib only.

Run the bundled worked example:

```
./verify.sh
```

## Verified output

```
=== bad ===
examples/bad/BucketAcl.java:9: aws-s3-java-canned-acl-public: SetBucketAclRequest req = new SetBucketAclRequest(bucket, CannedAccessControlList.PublicRead);
examples/bad/acl_calls.py:7: aws-s3-py-put-bucket-acl-public: s3.put_bucket_acl(
examples/bad/acl_calls.py:14: aws-s3-py-put-object-acl-public: s3.put_object_acl(
examples/bad/acl_calls.py:22: aws-s3-py-create-bucket-acl-public: s3.create_bucket(
examples/bad/policy_wildcard.py:14: aws-s3-bucket-policy-wildcard-principal-allow: "Principal": "*",
examples/bad/policy_wildcard.py:20: aws-s3-py-put-bucket-policy-wildcard-principal: s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
examples/bad/s3.js:6: aws-s3-js-put-bucket-acl-public: await client.send(new PutBucketAclCommand({
examples/bad/s3.js:17: aws-s3-bucket-policy-wildcard-principal-allow: Principal: '*',
examples/bad/s3.js:22: aws-s3-js-put-bucket-policy-wildcard-principal: await client.send(new PutBucketPolicyCommand({ Bucket: bucket, Policy: policy }));
examples/bad/acl.go:13: aws-s3-go-put-bucket-acl-public: ACL:    types.BucketCannedACLPublicReadWrite,
=== good ===
=== verify ===
bad findings:  10 (rc=1)
good findings: 0 (rc=0)
PASS
```
