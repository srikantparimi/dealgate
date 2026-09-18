# -----------------------------------------------------------------------------
# S2-E3: Agreements evidence bucket (`officeapp-<env>-agreements-<account>`).
#
# Sprint 2 shape (build-guide §12):
#   - Versioning ENABLED (every upload is a new version).
#   - SSE-AES256 default encryption on every PUT.
#   - Public-access-block ALL: no ACL, no policy grant, no public read.
#   - No CORS: uploads are server-signed PUT; no browser cross-origin call
#     needs to hit the bucket directly. If a future flow adds browser
#     downloads, add an aws_s3_bucket_cors_configuration then.
#
# Object Lock (WORM retention) is Sprint 4 territory — it must be set at
# bucket create time, so when the switch is flipped this bucket has to be
# replaced. Ticket: docs/backlog/s4-*-object-lock.md (to be filed).
#
# The API task's `AGREEMENTS_BUCKET` env var reads the value output below;
# the wave integrator wires that in when `module.storage` is added to root.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "agreements" {
  bucket        = "${var.name_prefix}-agreements-${var.account_id}"
  force_destroy = false

  tags = {
    Name    = "${var.name_prefix}-agreements"
    Purpose = "Legal NDA/MSA evidence uploads"
  }
}

resource "aws_s3_bucket_versioning" "agreements" {
  bucket = aws_s3_bucket.agreements.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "agreements" {
  bucket = aws_s3_bucket.agreements.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "agreements" {
  bucket = aws_s3_bucket.agreements.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Deliberately no aws_s3_bucket_cors_configuration — uploads happen via a
# server-signed pre-signed PUT and no browser download flow needs CORS.

# Lifecycle rule: expire non-current versions after 365 days so the bucket
# does not accumulate every superseded draft forever. Current versions
# are never expired here — retention lives with the DB row.
resource "aws_s3_bucket_lifecycle_configuration" "agreements" {
  bucket = aws_s3_bucket.agreements.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}

# -----------------------------------------------------------------------------
# S3-E5: SOW bucket (`officeapp-<env>-sows-<account>`).
#
# Shape mirrors the agreements bucket above — versioning ON, SSE-AES256,
# public-access-block ALL, no CORS. Each uploaded SOW becomes a new S3
# object (the `s3_key` is per-version) so the bucket-level versioning
# mostly protects against accidental overwrites; DB-level immutability of
# `sow_version` is the primary retention story.
#
# The API task's `SOW_BUCKET` env var reads the value output below; the
# wave integrator wires that in when `module.storage` is added to root.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "sows" {
  bucket        = "${var.name_prefix}-sows-${var.account_id}"
  force_destroy = false

  tags = {
    Name    = "${var.name_prefix}-sows"
    Purpose = "SOW uploads for AI extraction + human confirm (S3-E5)"
  }
}

resource "aws_s3_bucket_versioning" "sows" {
  bucket = aws_s3_bucket.sows.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sows" {
  bucket = aws_s3_bucket.sows.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "sows" {
  bucket = aws_s3_bucket.sows.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SOW uploads land server-signed PUT, so no CORS block is needed. If the
# confirm screen ever streams PDF bytes cross-origin from the browser
# (rather than the `<embed>` on the same-origin API-issued download URL),
# add an `aws_s3_bucket_cors_configuration` here.

resource "aws_s3_bucket_lifecycle_configuration" "sows" {
  bucket = aws_s3_bucket.sows.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}
