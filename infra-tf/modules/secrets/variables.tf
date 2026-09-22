variable "name_prefix" {
  description = "Name prefix for Secrets Manager secret names (e.g. officeapp-dev)."
  type        = string
}

# S7: every Secrets Manager secret in this module encrypts under the shared
# customer-managed CMK from modules/kms. Secrets Manager accepts kms_key_id
# updates in place — no data migration required; first read after the switch
# decrypts against the new key.
variable "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used to encrypt every secret in this module."
  type        = string
}
