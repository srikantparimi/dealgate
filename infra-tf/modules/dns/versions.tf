terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
      # Both regional and us-east-1 aliases are required — us-east-1 for the
      # CloudFront-attachable ACM cert, default for zone + records + SES.
      configuration_aliases = [aws.us_east_1]
    }
  }
}
