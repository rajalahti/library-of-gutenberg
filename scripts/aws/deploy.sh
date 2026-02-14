#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

STACK_NAME="${STACK_NAME:-library-of-gutenberg}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
AWS_REGION="${AWS_REGION:-eu-north-1}"
DOMAIN_NAME="${DOMAIN_NAME:-library.rajalahti.me}"
ROOT_DOMAIN="${ROOT_DOMAIN:-rajalahti.me}"
HOSTED_ZONE_ID="${HOSTED_ZONE_ID:-}"
CERT_ARN="${CERT_ARN:-}"
CERT_MATCH_DOMAIN="${CERT_MATCH_DOMAIN:-*.rajalahti.me}"
INVALIDATE_CF="${INVALIDATE_CF:-false}"

if [[ -z "${HOSTED_ZONE_ID}" ]]; then
  HOSTED_ZONE_ID="$(aws route53 list-hosted-zones-by-name \
    --dns-name "${ROOT_DOMAIN}" \
    --query "HostedZones[?Name=='${ROOT_DOMAIN}.']|[0].Id" \
    --output text | sed 's#^/hostedzone/##')"
fi

if [[ -z "${HOSTED_ZONE_ID}" || "${HOSTED_ZONE_ID}" == "None" ]]; then
  echo "Failed to resolve HostedZoneId for ${ROOT_DOMAIN}" >&2
  exit 1
fi

if [[ -z "${CERT_ARN}" ]]; then
  CERT_ARN="$(aws acm list-certificates \
    --region us-east-1 \
    --certificate-statuses ISSUED \
    --query "(CertificateSummaryList[?DomainName=='${CERT_MATCH_DOMAIN}' || DomainName=='${ROOT_DOMAIN}' || contains(SubjectAlternativeNameSummaries, '${CERT_MATCH_DOMAIN}')])[0].CertificateArn" \
    --output text)"
fi

if [[ -z "${CERT_ARN}" || "${CERT_ARN}" == "None" ]]; then
  echo "Failed to resolve ACM certificate in us-east-1 matching ${CERT_MATCH_DOMAIN}" >&2
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-${STACK_NAME}-artifacts-${ACCOUNT_ID}-${AWS_REGION}}"

if [[ -z "${STATIC_BUCKET_NAME:-}" ]]; then
  RAW_BUCKET_NAME="${STACK_NAME}-${DOMAIN_NAME}-${ACCOUNT_ID}-${AWS_REGION}"
  STATIC_BUCKET_NAME="$(echo "${RAW_BUCKET_NAME}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9-' '-' | sed 's/^-*//; s/-*$//' | cut -c1-63)"
  STATIC_BUCKET_NAME="${STATIC_BUCKET_NAME%-}"
fi

if ! aws s3api head-bucket --bucket "${ARTIFACT_BUCKET}" >/dev/null 2>&1; then
  if [[ "${AWS_REGION}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${ARTIFACT_BUCKET}" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "${ARTIFACT_BUCKET}" \
      --create-bucket-configuration LocationConstraint="${AWS_REGION}" >/dev/null
  fi
fi

BUILD_OUTPUT="$(${ROOT_DIR}/scripts/aws/build_artifacts.sh)"
LAMBDA_ZIP="$(echo "${BUILD_OUTPUT}" | awk -F= '/^lambda_zip=/{print $2}')"
LAMBDA_SHA256="$(echo "${BUILD_OUTPUT}" | awk -F= '/^lambda_sha256=/{print $2}')"
SITE_DIR="$(echo "${BUILD_OUTPUT}" | awk -F= '/^site_dir=/{print $2}')"

if [[ -z "${LAMBDA_ZIP}" || -z "${LAMBDA_SHA256}" || -z "${SITE_DIR}" ]]; then
  echo "Artifact build step failed to produce expected outputs" >&2
  exit 1
fi

LAMBDA_CODE_KEY="${STACK_NAME}/lambda/${LAMBDA_SHA256}.zip"

aws s3 cp "${LAMBDA_ZIP}" "s3://${ARTIFACT_BUCKET}/${LAMBDA_CODE_KEY}" >/dev/null

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file "${ROOT_DIR}/infra/aws/cloudformation.yml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    DomainName="${DOMAIN_NAME}" \
    HostedZoneId="${HOSTED_ZONE_ID}" \
    CertificateArn="${CERT_ARN}" \
    LambdaCodeBucket="${ARTIFACT_BUCKET}" \
    LambdaCodeKey="${LAMBDA_CODE_KEY}" \
    StaticBucketName="${STATIC_BUCKET_NAME}"

SITE_BUCKET="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue | [0]" \
  --output text)"

DISTRIBUTION_ID="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue | [0]" \
  --output text)"

SITE_URL="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue | [0]" \
  --output text)"

aws s3 sync "${SITE_DIR}/" "s3://${SITE_BUCKET}/" \
  --delete \
  --exclude "index.html" \
  --cache-control "public,max-age=86400" >/dev/null

aws s3 cp "${SITE_DIR}/index.html" "s3://${SITE_BUCKET}/index.html" \
  --cache-control "public,max-age=60,must-revalidate" \
  --content-type "text/html; charset=utf-8" >/dev/null

if [[ "${INVALIDATE_CF}" == "true" ]]; then
  aws cloudfront create-invalidation \
    --distribution-id "${DISTRIBUTION_ID}" \
    --paths "/index.html" "/" >/dev/null
fi

echo "Deployed stack: ${STACK_NAME}"
echo "Region: ${AWS_REGION}"
echo "Domain: ${DOMAIN_NAME}"
echo "Site URL: ${SITE_URL}"
echo "CloudFront distribution: ${DISTRIBUTION_ID}"
echo "Static bucket: ${SITE_BUCKET}"
