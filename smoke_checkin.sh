#!/usr/bin/env bash
# Simple smoke test for check-in service health endpoints.
# Usage:
#   BASE_URL=http://localhost:8006 ./smoke_checkin.sh
# Defaults BASE_URL to http://localhost:8006 when not set.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8006}"

tmpfile="$(mktemp)"
cleanup() { rm -f "$tmpfile"; }
trap cleanup EXIT

check_endpoint() {
  local path="$1"
  local url="${BASE_URL%/}${path}"
  echo "Checking ${url} ..."
  local code
  code="$(curl -s -o "$tmpfile" -w "%{http_code}" "$url")"

  if [[ "$code" != "200" ]]; then
    echo "❌ ${path} failed (HTTP ${code}):"
    cat "$tmpfile"
    exit 1
  fi

  echo "✅ ${path} ok: $(cat "$tmpfile")"
}

check_endpoint "/health"
check_endpoint "/db-health"

echo "All smoke checks passed."
