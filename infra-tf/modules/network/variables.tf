variable "name_prefix" {
  description = "Prefix applied to Name tags on every VPC resource (e.g. officeapp-dev)."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC. /16 leaves room for four /20 subnets and future workloads."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Two /20 CIDRs for the public subnets (ALB, NAT)."
  type        = list(string)
  default     = ["10.42.0.0/20", "10.42.16.0/20"]
}

variable "private_subnet_cidrs" {
  description = "Two /20 CIDRs for the private subnets (ECS tasks, RDS)."
  type        = list(string)
  default     = ["10.42.32.0/20", "10.42.48.0/20"]
}
