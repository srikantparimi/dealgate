variable "name_prefix" {
  description = "Name prefix (e.g. officeapp-dev)."
  type        = string
}

variable "account_id" {
  description = "AWS account id — appended to the bucket name for global uniqueness."
  type        = string
}

# S7: KMS-at-rest wiring. All buckets in this module switch from SSE-AES256
# to aws:kms using the shared customer-managed key from `modules/kms`.
variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used for SSE-KMS on every bucket in this module."
  type        = string
}

# S7: signed-SOW Object Lock retention. GOVERNANCE mode + 3-year default per
# blueprint §12. Set per-env if the retention window differs (prod may want 7y).
variable "sow_object_lock_years" {
  description = "Object Lock retention (in years) applied by default to every new PUT into the sows bucket. GOVERNANCE mode."
  type        = number
  default     = 3
}

# S7: audit-exports Object Lock retention. COMPLIANCE mode + 7-year default
# per blueprint §12. COMPLIANCE means no principal — including root — can
# delete or edit a locked object before retention expires.
variable "audit_export_retention_years" {
  description = "Object Lock retention (in years) applied by default to every PUT into the audit-exports bucket. COMPLIANCE mode."
  type        = number
  default     = 7
}
