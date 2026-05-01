// Safe shape: private bucket, all public-access-block knobs ON,
// and a bucket policy whose Principal is an explicit account.

resource "aws_s3_bucket" "site" {
  bucket = "my-private-bucket"
}

resource "aws_s3_bucket_acl" "site" {
  bucket = aws_s3_bucket.site.id
  acl    = "private"
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowSpecificRole"
        Effect    = "Allow"
        Principal = { "AWS" : "arn:aws:iam::123456789012:role/AppRole" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.site.arn}/*"
      }
    ]
  })
}

resource "aws_s3_bucket_cors_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  cors_rule {
    allowed_methods = ["GET"]
    allowed_origins = ["https://app.example.com"]
  }
}
