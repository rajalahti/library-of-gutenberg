#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="${ROOT_DIR}/.dist"
LAMBDA_BUILD_DIR="${DIST_DIR}/lambda"
SITE_BUILD_DIR="${DIST_DIR}/site"

rm -rf "${LAMBDA_BUILD_DIR}" "${SITE_BUILD_DIR}" "${DIST_DIR}/lambda.zip"
mkdir -p "${LAMBDA_BUILD_DIR}" "${SITE_BUILD_DIR}"

cp "${ROOT_DIR}/lambda/index.mjs" "${LAMBDA_BUILD_DIR}/index.mjs"
cp -R "${ROOT_DIR}/data" "${LAMBDA_BUILD_DIR}/data"

(
  cd "${LAMBDA_BUILD_DIR}"
  zip -qr "${DIST_DIR}/lambda.zip" .
)

cp "${ROOT_DIR}/index.html" "${SITE_BUILD_DIR}/index.html"
cp -R "${ROOT_DIR}/images" "${SITE_BUILD_DIR}/images"
cp -R "${ROOT_DIR}/data" "${SITE_BUILD_DIR}/data"

if command -v shasum >/dev/null 2>&1; then
  LAMBDA_SHA256="$(shasum -a 256 "${DIST_DIR}/lambda.zip" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  LAMBDA_SHA256="$(sha256sum "${DIST_DIR}/lambda.zip" | awk '{print $1}')"
else
  echo "Unable to find shasum or sha256sum" >&2
  exit 1
fi

echo "lambda_zip=${DIST_DIR}/lambda.zip"
echo "lambda_sha256=${LAMBDA_SHA256}"
echo "site_dir=${SITE_BUILD_DIR}"
