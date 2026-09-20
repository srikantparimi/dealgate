# Data lookup for the API ALB. The api module creates it independently; we
# reference it here as a CloudFront origin so the browser can talk to the API
# over HTTPS via /api/*. Using a data source avoids a module cycle
# (web -> auth -> api -> web). Bootstrap needs the ALB to exist before the
# first plan that includes this behavior — first-apply order in docs.
data "aws_lb" "api" {
  name = "${var.name_prefix}-alb"
}

# Private origin bucket for the SPA build.
resource "aws_s3_bucket" "web" {
  bucket = "${var.name_prefix}-web-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "web" {
  bucket = aws_s3_bucket.web.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    apply_server_side_encryption_by_default {
      # S7: was AES256; move to customer-managed KMS for consistency with the
      # rest of the stack. CloudFront reads via OAC — the OAC principal is
      # granted access to the CMK by the delegated-service statement in the
      # KMS key policy (kms:ViaService = s3.<region>.amazonaws.com), so no
      # extra grant is needed here.
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    # Bucket key on the SPA bucket cuts KMS API cost to nearly zero — every
    # GET on index.html and the JS bundles would otherwise hit KMS.
    bucket_key_enabled = true
  }
}

# Origin Access Control (replaces legacy OAI).
resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name_prefix}-web-oac"
  description                       = "OAC for ${var.name_prefix} SPA bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "strip_api_prefix" {
  name    = "${var.name_prefix}-strip-api"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite /api/* to /* before forwarding to the ALB origin."
  publish = true
  code    = <<-JS
    function handler(event) {
      var req = event.request;
      if (req.uri.indexOf('/api/') === 0) {
        req.uri = req.uri.substring(4); // drop leading "/api"
      } else if (req.uri === '/api') {
        req.uri = '/';
      }
      return req;
    }
  JS
}

resource "aws_cloudfront_response_headers_policy" "web" {
  name = "${var.name_prefix}-web-headers"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.name_prefix} SPA"
  default_root_object = "index.html"
  price_class         = "PriceClass_100" # US + EU only; cheapest

  # An alias is only legal when viewer_certificate carries a matching ACM cert,
  # so both are driven off the same pair of variables and move together.
  aliases = var.domain_name == "" ? [] : [var.domain_name]

  origin {
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_id                = "s3-${aws_s3_bucket.web.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    domain_name = data.aws_lb.api.dns_name
    origin_id   = "alb-api"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3-${aws_s3_bucket.web.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS-managed CachingOptimized policy
    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    response_headers_policy_id = aws_cloudfront_response_headers_policy.web.id
  }

  # /api/* proxies to the ALB; disable caching, forward everything.
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "alb-api"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS-managed CachingDisabled + AllViewer origin request policies.
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.strip_api_prefix.arn
    }
  }

  # SPA fallback: rewrite 403/404 to index.html so client-side routing works.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # With no certificate supplied this is CloudFront's default *.cloudfront.net
  # cert. With one, we switch to SNI (the dedicated-IP alternative costs ~$600
  # a month) and raise the floor to TLSv1.2_2021 — the default cert's TLSv1
  # floor is only tolerable because nobody types that hostname.
  viewer_certificate {
    cloudfront_default_certificate = var.acm_certificate_arn == "" ? true : null
    acm_certificate_arn            = var.acm_certificate_arn == "" ? null : var.acm_certificate_arn
    ssl_support_method             = var.acm_certificate_arn == "" ? null : "sni-only"
    minimum_protocol_version       = var.acm_certificate_arn == "" ? null : "TLSv1.2_2021"
  }
}

# Bucket policy allowing this distribution (via OAC) to read objects.
data "aws_iam_policy_document" "web_bucket" {
  statement {
    effect  = "Allow"
    actions = ["s3:GetObject"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    resources = ["${aws_s3_bucket.web.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web_bucket.json
}
