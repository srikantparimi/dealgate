mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
}

override_resource {
  target = aws_cloudfront_function.spa_rewrite
  values = { arn = "arn:aws:cloudfront::123456789012:function/spa-rewrite" }
}
override_resource {
  target = aws_cloudfront_function.strip_api_prefix
  values = { arn = "arn:aws:cloudfront::123456789012:function/strip-api" }
}

variables {
  name_prefix = "officeapp-test"
  account_id  = "123456789012"
  kms_key_arn = "arn:aws:kms:us-east-2:123456789012:key/00000000-0000-0000-0000-000000000001"
}

run "spa_only_fallback_and_uncached_api_errors" {
  command = apply

  assert {
    condition = aws_cloudfront_distribution.web.default_cache_behavior[0].function_association == toset([{
      event_type = "viewer-request", function_arn = aws_cloudfront_function.spa_rewrite.arn
    }])
    error_message = "The SPA needs a behavior-scoped request rewrite."
  }
  assert {
    condition = toset([for behavior in aws_cloudfront_distribution.web.ordered_cache_behavior : behavior.path_pattern]) == toset(["/api", "/api/*"]) && alltrue([
      for behavior in aws_cloudfront_distribution.web.ordered_cache_behavior :
      behavior.target_origin_id == "alb-api" && behavior.cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" && behavior.function_association == toset([{
        event_type = "viewer-request", function_arn = aws_cloudfront_function.strip_api_prefix.arn
      }])
    ])
    error_message = "API paths must reach the ALB with CachingDisabled."
  }
  assert {
    condition = toset([for error in aws_cloudfront_distribution.web.custom_error_response : error.error_code]) == toset([400, 403, 404, 405, 414, 500, 501, 502, 503, 504]) && alltrue([
      for error in aws_cloudfront_distribution.web.custom_error_response :
      error.error_caching_min_ttl == 0 && coalesce(error.response_page_path, "none") == "none" && coalesce(tostring(error.response_code), "0") == "0"
    ])
    error_message = "Errors must keep their original status/body and use zero error TTL."
  }
}
