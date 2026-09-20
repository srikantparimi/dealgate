# Runbook — putting DealGate on dealgate.smartek21.com

The app is served by CloudFront distribution `E1XAQZCROIFYG7` in account
`669810405473`. This runbook attaches a custom domain to it.

**The DNS for `smartek21.com` is on Cloudflare, not Route53.** There is no
hosted zone for it in this AWS account and there never has been. Every step
below that touches DNS is a manual action in the Cloudflare dashboard, and
Terraform cannot do it for you.

That is not a theoretical limitation. ACM certificate
`fee46cbc-6499-4a59-a6ca-300d04c742ba` for `training.smartek21.com` was
requested on 1 July 2026 and expired unvalidated (`VALIDATION_TIMED_OUT`)
because nobody ever added its CNAME in Cloudflare. **ACM gives you 72 hours.**

## Current state

| | Value |
|---|---|
| Distribution | `E1XAQZCROIFYG7` |
| CloudFront hostname | `d1mu2un4hj9akj.cloudfront.net` |
| Certificate (us-east-1) | `arn:aws:acm:us-east-1:669810405473:certificate/be843eb6-0545-4c59-a18d-2b79a2b8ef7c` |
| Cognito user pool | `us-east-2_VV03Ir8AF` |
| Cognito app client | `dg2b6dhiu126bq459tthcmso2` |

## Step 1 — Validate the certificate (Cloudflare)

Add this CNAME. Proxy status must be **DNS only** (grey cloud); Cloudflare will
not proxy an underscore-prefixed record anyway, but a proxied record here fails
validation silently.

| Field | Value |
|---|---|
| Type | `CNAME` |
| Name | `_ffc72f4d96a00907036becbb91b0e0c4.dealgate` |
| Target | `_bbabf83d7058f421aa70084b37e52a07.wzccmgtwzk.acm-validations.aws` |
| Proxy | DNS only |
| TTL | Auto |

Cloudflare appends the zone name to `Name`, so enter `…c4.dealgate`, **not**
the fully-qualified `…c4.dealgate.smartek21.com`. If you paste the FQDN
Cloudflare usually strips the suffix itself — check the saved record reads
`_ffc72f4d96a00907036becbb91b0e0c4.dealgate.smartek21.com` exactly once, not
twice.

Confirm from a terminal, then poll ACM:

```bash
dig +short CNAME _ffc72f4d96a00907036becbb91b0e0c4.dealgate.smartek21.com

aws acm describe-certificate --region us-east-1 \
  --certificate-arn arn:aws:acm:us-east-1:669810405473:certificate/be843eb6-0545-4c59-a18d-2b79a2b8ef7c \
  --query 'Certificate.Status' --output text
```

Wait for `ISSUED`. Typically a few minutes. Do not continue before it is issued
— CloudFront rejects an alias whose certificate is still pending, and the
failure leaves the distribution mid-update.

## Step 2 — Attach the alias to CloudFront

CloudFront has no "add alias" verb; you fetch the whole config, edit it, and
PUT it back with the current ETag as `--if-match`.

```bash
DIST=E1XAQZCROIFYG7
CERT=arn:aws:acm:us-east-1:669810405473:certificate/be843eb6-0545-4c59-a18d-2b79a2b8ef7c

aws cloudfront get-distribution-config --id "$DIST" > /tmp/dist.json
ETAG=$(python3 -c "import json;print(json.load(open('/tmp/dist.json'))['ETag'])")

python3 - <<PY
import json
d = json.load(open('/tmp/dist.json'))['DistributionConfig']
d['Aliases'] = {'Quantity': 1, 'Items': ['dealgate.smartek21.com']}
d['ViewerCertificate'] = {
    'ACMCertificateArn': "$CERT",
    'SSLSupportMethod': 'sni-only',
    'MinimumProtocolVersion': 'TLSv1.2_2021',
    'Certificate': "$CERT",
    'CertificateSource': 'acm',
}
json.dump(d, open('/tmp/dist-new.json', 'w'))
PY

aws cloudfront update-distribution --id "$DIST" \
  --if-match "$ETAG" --distribution-config file:///tmp/dist-new.json
```

Then wait for the distribution to leave `InProgress` (5–10 minutes):

```bash
aws cloudfront wait distribution-deployed --id E1XAQZCROIFYG7
```

## Step 3 — Point the domain at CloudFront (Cloudflare)

| Field | Value |
|---|---|
| Type | `CNAME` |
| Name | `dealgate` |
| Target | `d1mu2un4hj9akj.cloudfront.net` |
| Proxy | **DNS only (grey cloud)** |
| TTL | Auto |

**Leave the proxy off.** With the orange cloud on, Cloudflare terminates TLS
with its own certificate and forwards to CloudFront, which then sees a Host
header it has an alias for but a connection it did not terminate. It can be
made to work with Cloudflare SSL mode "Full (strict)", but it doubles the CDN
layers, hides CloudFront's logs and cache behaviour, and buys nothing — the
content is already on a CDN.

## Step 4 — Let Cognito accept the new origin

Adding, not replacing: the CloudFront URLs stay so anyone mid-session is not
logged out, and a DNS problem stays cosmetic instead of becoming an outage.

`update-user-pool-client` **replaces the entire client configuration**. Every
field below must be present or it is silently reset — token lifetimes, auth
flows and OAuth scopes included.

```bash
aws cognito-idp update-user-pool-client \
  --region us-east-2 \
  --user-pool-id us-east-2_VV03Ir8AF \
  --client-id dg2b6dhiu126bq459tthcmso2 \
  --client-name officeapp-dev-web \
  --refresh-token-validity 30 \
  --access-token-validity 60 \
  --id-token-validity 60 \
  --token-validity-units AccessToken=minutes,IdToken=minutes,RefreshToken=days \
  --explicit-auth-flows ALLOW_REFRESH_TOKEN_AUTH ALLOW_USER_SRP_AUTH \
  --supported-identity-providers COGNITO \
  --callback-urls "http://localhost:5173/auth/callback" \
                  "https://d1mu2un4hj9akj.cloudfront.net/auth/callback" \
                  "https://dealgate.smartek21.com/auth/callback" \
  --logout-urls "http://localhost:5173/" \
                "https://d1mu2un4hj9akj.cloudfront.net/" \
                "https://dealgate.smartek21.com/" \
  --allowed-o-auth-flows code \
  --allowed-o-auth-scopes email openid profile \
  --allowed-o-auth-flows-user-pool-client \
  --prevent-user-existence-errors ENABLED \
  --enable-token-revocation \
  --no-enable-propagate-additional-user-context-data \
  --auth-session-validity 3
```

Diff the result against the previous config before walking away.

## Step 5 — Verify

```bash
curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' https://dealgate.smartek21.com
openssl s_client -connect dealgate.smartek21.com:443 -servername dealgate.smartek21.com </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

Then in a browser: load `https://dealgate.smartek21.com`, sign in through
Cognito, and confirm the redirect lands back on the new host and not on
`d1mu2un4hj9akj.cloudfront.net`.

## Terraform

The stack now models all of this — `var.domain`, `aws_acm_certificate.web`,
the distribution alias, and the Cognito callbacks. It has **not** been applied,
and `terraform apply` on this stack is currently unsafe for an unrelated
reason: `module.kms` is missing from the local state, so a plain apply proposes
a `kms_key_id` change on `officeapp-dev-db` that is a ForceNew replacement.
`prevent_destroy` now turns that into a hard error rather than a deleted
database, but the apply still will not complete.

To reconcile the code with reality later, import rather than apply:

```bash
terraform import 'aws_acm_certificate.web[0]' \
  arn:aws:acm:us-east-1:669810405473:certificate/be843eb6-0545-4c59-a18d-2b79a2b8ef7c
```

The distribution and Cognito client are already in state; a `terraform plan`
after import should show no diff for them if the hand-applied values match the
code. If it shows one, the code is wrong — fix the code, not the environment.

## Rolling back

The CloudFront hostname keeps working throughout, so rollback is only needed if
the alias itself breaks something:

1. Delete the `dealgate` CNAME in Cloudflare — traffic stops reaching the alias.
2. Re-run Step 2 with `Aliases` set to `{'Quantity': 0}` and `ViewerCertificate`
   back to `{'CloudFrontDefaultCertificate': True, 'MinimumProtocolVersion': 'TLSv1', 'SSLSupportMethod': 'vip', 'CertificateSource': 'cloudfront'}`.
3. Leave the Cognito URLs in place; extra callback URLs are harmless.
