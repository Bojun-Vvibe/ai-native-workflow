# llm-output-terraform-aws-s3-public-acl-detector

Static detector for Terraform HCL that exposes an AWS S3 bucket to
the public internet via a permissive ACL, a permissive bucket policy,
or a disabled `aws_s3_bucket_public_access_block`.

This is the canonical CWE-732 / CWE-284 LLM footgun: when asked for
"a quick S3 bucket I can drop files into", a language model will
emit the legacy `acl = "public-read"` shape, or skip the public-
access-block resource entirely, or paste an `s3:GetObject` policy
with `Principal = "*"` and no condition.

```hcl
# CWE-732: world-readable bucket
resource "aws_s3_bucket" "site" {
  bucket = "my-site"
  acl    = "public-read"        # flagged
}

resource "aws_s3_bucket_acl" "site" {
  bucket = aws_s3_bucket.site.id
  acl    = "public-read-write"  # flagged
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = false   # flagged
  block_public_policy     = false   # flagged
  ignore_public_acls      = false   # flagged
  restrict_public_buckets = false   # flagged
}
```

The safe shape is private ACL + a fully-on public-access-block + a
bucket policy whose `Principal` is a specific account / role / OAC,
never `"*"`:

```hcl
resource "aws_s3_bucket" "site" {
  bucket = "my-site"
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

## What this flags

Six related shapes:

1. **tf-s3-acl-public** — `acl = "public-read"` /
   `acl = "public-read-write"` / `acl = "authenticated-read"` inside
   either `aws_s3_bucket` or `aws_s3_bucket_acl`.
2. **tf-s3-pab-disabled** — any of the four `aws_s3_bucket_public_access_block`
   booleans set to `false`.
3. **tf-s3-pab-missing** — an `aws_s3_bucket` whose `bucket = "..."`
   appears in the file but no `aws_s3_bucket_public_access_block`
   resource exists in the same file. Reported once per file.
4. **tf-s3-policy-principal-wildcard** — an `aws_s3_bucket_policy`
   (or inline `policy = jsonencode({...})`) containing
   `"Principal": "*"` or `"Principal": { "AWS": "*" }` without an
   accompanying `Condition` block.
5. **tf-s3-website-public** — `aws_s3_bucket_website_configuration`
   on a bucket that also has a permissive ACL. Reported as a paired
   amplifier.
6. **tf-s3-cors-allow-all-origins** — `aws_s3_bucket_cors_configuration`
   with `allowed_origins = ["*"]`.

A finding is suppressed if the same logical line carries
`# llm-allow:tf-s3-public`.

## CWE references

* **CWE-732**: Incorrect Permission Assignment for Critical Resource.
* **CWE-284**: Improper Access Control.
* **CWE-359**: Exposure of Private Personal Information to an
  Unauthorized Actor (when the bucket holds PII).

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.
Scans `.tf` and `.tf.json` files, plus fenced ` ```hcl ` /
` ```terraform ` / ` ```tf ` blocks in Markdown.

## Worked example

```
$ bash verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/main.tf` and `examples/good/main.tf` for fixtures.
