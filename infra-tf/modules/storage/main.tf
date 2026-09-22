# -----------------------------------------------------------------------------
# S2-E3: Agreements evidence bucket (`officeapp-<env>-agreements-<account>`).
#
# Sprint 2 shape (build-guide §12):
#   - Versioning ENABLED (every upload is a new version).
#   - SSE-KMS default encryption on every PUT (S7: was AES256).
#   - Public-access-block ALL: no ACL, no policy grant, no public read.
#   - No CORS: uploads are server-signed PUT; no browser cross-origin call
#     needs to hit the bucket directly. If a future flow adds browser
#     downloads, add an aws_s3_bucket_cors_configuration then.
#
# S7 note: switching SSE from AES256 to aws:kms is an in-place bucket-property
# update. Existing objects keep their AES-256 encryption; new PUTs use the CMK.
# No data migration required. If you want existing objects re-encrypted,
# `aws s3 cp` them onto themselves with --sse aws:kms --sse-kms-key-id.
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
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    # Bucket keys still valid with SSE-KMS and cut per-object KMS API cost by ~99%.
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
# Shape mirrors the agreements bucket above — versioning ON, SSE-KMS (S7),
# public-access-block ALL, no CORS. Each uploaded SOW becomes a new S3
# object (the `s3_key` is per-version) so the bucket-level versioning
# mostly protects against accidental overwrites; DB-level immutability of
# `sow_version` is the primary retention story.
#
# S7: Object Lock (GOVERNANCE, 3y) on the signed-SOW prefix `signed/*`.
#
# IMPORTANT CAVEAT: Object Lock must be enabled *at bucket create time*
# (`object_lock_enabled = true` on `aws_s3_bucket`). Terraform's provider
# treats a change to that attribute as a ForceNew — flipping it on an
# existing bucket will destroy-and-recreate the bucket, which drops every
# object in it. The dev bucket may already exist without object_lock_enabled;
# integrators must either:
#   (a) accept the recreate (dev-only data, throwaway), or
#   (b) do a manual migration: rename the existing bucket via aws-cli
#       `mv`, then `terraform apply` to create the new lock-enabled bucket,
#       then copy objects from old to new with `aws s3 sync`.
#
# Existing objects uploaded BEFORE Object Lock was enabled do NOT
# retroactively get a retention lock — only PUTs after the configuration
# is in place inherit the default retention.
#
# The API task's `SOW_BUCKET` env var reads the value output below; the
# wave integrator wires that in when `module.storage` is added to root.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "sows" {
  bucket        = "${var.name_prefix}-sows-${var.account_id}"
  force_destroy = false

  # S7: enables the aws_s3_bucket_object_lock_configuration below. Required at
  # create time. See caveat above about existing buckets.
  object_lock_enabled = true

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
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
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

# -----------------------------------------------------------------------------
# S7: Object Lock default retention on the sows bucket.
#
# GOVERNANCE mode = a special IAM permission (s3:BypassGovernanceRetention)
# can override the lock; COMPLIANCE mode = *nobody* including root can
# delete until retention expires. GOVERNANCE is the right choice here
# because the signed-SOW record's immutability is enforced primarily in
# the database (sow_version rows are append-only) and the S3 lock is a
# belt-and-braces "no accidental overwrite" guarantee.
#
# Retention days is set from years * 365 so per-env overrides (prod = 7y)
# just bump the variable.
#
# Existing objects uploaded before this configuration was applied are NOT
# retroactively locked. Only PUTs after apply inherit the default.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket_object_lock_configuration" "sows" {
  bucket = aws_s3_bucket.sows.id

  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = var.sow_object_lock_years * 365
    }
  }

  # Versioning + object-lock-enabled must both be in place before the config
  # can attach; make the ordering explicit for first-apply.
  depends_on = [aws_s3_bucket_versioning.sows]
}

# -----------------------------------------------------------------------------
# S7: audit-exports bucket (`officeapp-<env>-audit-exports-<account>`).
#
# The nightly `worker.audit_export` (see `worker/audit_export.py`) ships one
# gzipped JSONL per day of `audit_event` rows to this bucket. Blueprint §12
# requires an off-database WORM copy so a compromise of the RDS instance
# cannot silently rewrite history.
#
# Bucket shape:
#   - Object Lock in COMPLIANCE mode, 7-year default retention. COMPLIANCE
#     (not GOVERNANCE) is deliberate: nobody — including the account root —
#     can delete a locked object before its retention window expires. This
#     is the audit trail's off-site immutability guarantee.
#   - Versioning ENABLED (mandatory for Object Lock; also captures the
#     sidecar `audit-r{n}.jsonl.gz` files the worker writes on md5-mismatch
#     drift).
#   - SSE-KMS with the shared CMK (merged with Agent FF's cross-bucket KMS
#     switch). Falls back to AES256 semantics for reviewers reading the older
#     story text — the wire format on the worker's PUT is unchanged.
#   - Public-access-block ALL: no ACL, no policy grant, no public read.
#   - No lifecycle rule that deletes: retention is Object Lock. A future
#     story can add a Glacier *transition* for cost, but never a delete.
#
# Same caveat as the sows bucket: Object Lock must be enabled at bucket
# create time. The dev bucket does not exist yet (this is a new resource);
# for prod, the integrator creates it once and never flips `object_lock_enabled`.
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "audit_exports" {
  bucket              = "${var.name_prefix}-audit-exports-${var.account_id}"
  force_destroy       = false
  object_lock_enabled = true

  tags = {
    Name = "${var.name_prefix}-audit-exports"
    # S14a.3 (22 Sep 2026): AWS S3 tag values only allow letters, numbers,
    # whitespace, and + - = . _ : / @. The original had an em-dash and
    # parentheses/commas — all of which S3 rejects with InvalidTag.
    Purpose = "Nightly audit_event export WORM 7-year retention S7"
  }
}

resource "aws_s3_bucket_versioning" "audit_exports" {
  bucket = aws_s3_bucket.audit_exports.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_exports" {
  bucket = aws_s3_bucket.audit_exports.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit_exports" {
  bucket = aws_s3_bucket.audit_exports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "audit_exports" {
  bucket = aws_s3_bucket.audit_exports.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = var.audit_export_retention_years
    }
  }

  depends_on = [aws_s3_bucket_versioning.audit_exports]
}
