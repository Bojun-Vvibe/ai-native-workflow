# llm-output-minio-anonymous-bucket-policy-detector

Detects MinIO / S3-style bucket policy JSON files that grant
anonymous (`Principal: "*"` or `{"AWS": "*"}`) write, list, or
wildcard access — the exact shape `mc anonymous set public` writes
and that LLM quickstart blog posts copy verbatim.

## Why this matters

A policy with `Effect: Allow`, `Principal: "*"`, and `Action: s3:*`
turns a MinIO bucket into a public read/write/delete drop box on the
internet. The well-known *public read-only static site* shape, by
contrast, restricts the action to `s3:GetObject` against object-key
ARNs (`arn:aws:s3:::bucket/*`), which is documented and acceptable.

This detector tells the difference.

## Rules

For each statement in the policy:

1. `Effect` must be `Allow` (case-insensitive).
2. `Principal` must evaluate to anonymous: literal `"*"`,
   `{"AWS": "*"}`, or `{"AWS": ["*"]}`.
3. The statement is flagged when its action set contains any of:
   - `s3:*` or `*` — full anonymous control.
   - `s3:PutObject`, `s3:DeleteObject`, `s3:PutObjectAcl`,
     `s3:DeleteBucket`, `s3:PutBucketPolicy` — anonymous writes.
   - `s3:ListBucket` / `s3:ListBucketMultipartUploads` against a
     bucket-root ARN — anonymous enumeration.
   - `s3:GetObject` against a bucket-root ARN (no `/*` suffix) —
     unusual / probably a typo.
4. Anonymous `s3:GetObject` against an object-key ARN
   (`arn:aws:s3:::bucket/*`) is *not* flagged: that is the
   documented public-static-site pattern.

A line containing the marker `minio-anonymous-allowed` (e.g. a
`// minio-anonymous-allowed` JSONC comment, or a `"_comment"` field)
suppresses the finding for the whole file.

## Run

```
python3 detector.py examples/bad/01_anonymous_s3_star.json
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Out of scope

* MinIO IAM user/group policies (different document shape).
* AWS S3 ACLs (`AccessControlPolicy` XML).
* Cross-account `Principal: {"AWS": "arn:aws:iam::OTHER:..."}` —
  named principals are not anonymous and need a separate review.
