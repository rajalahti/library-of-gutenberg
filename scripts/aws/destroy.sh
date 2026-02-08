#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${STACK_NAME:-library-of-gutenberg}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
AWS_REGION="${AWS_REGION:-eu-north-1}"

if ! aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" >/dev/null 2>&1; then
  echo "Stack ${STACK_NAME} does not exist in ${AWS_REGION}."
  exit 0
fi

SITE_BUCKET="$(aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue | [0]" \
  --output text)"

if [[ -n "${SITE_BUCKET}" && "${SITE_BUCKET}" != "None" ]]; then
  aws s3 rm "s3://${SITE_BUCKET}" --recursive >/dev/null || true
fi

aws cloudformation delete-stack --region "${AWS_REGION}" --stack-name "${STACK_NAME}"
aws cloudformation wait stack-delete-complete --region "${AWS_REGION}" --stack-name "${STACK_NAME}"

echo "Deleted stack ${STACK_NAME} in ${AWS_REGION}."
