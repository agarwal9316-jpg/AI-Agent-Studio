#!/usr/bin/env bash
# Sign portable AI-Agent-Studio EXE(s) via osslsigncode (cross-platform helper).
# Pipeline only — certificate is USER-PROVIDED. Self-signed is for DEV ONLY (not distribution trust).
#
# Usage:
#   ./scripts/sign_portable.sh                  # sign dist/AI-Agent-Studio/*.exe
#   ./scripts/sign_portable.sh path/to/file.exe
#   ./scripts/sign_portable.sh --dry-run
#   ./scripts/sign_portable.sh --help
#
# Env:
#   AAS_SIGN_CERT       Path to .pfx / .p12
#   AAS_SIGN_PASSWORD   PFX password
#   AAS_SIGN_TIMESTAMP  Timestamp URL (default DigiCert)
#   AAS_SIGN_SKIP=1     Force skip (exit 0)
#   AAS_SIGN_SELF_SIGNED_DEV=1  Allow untrusted/self-signed (DEV ONLY)
#
# Exit: 0 = signed or gracefully skipped; 1 = hard failure after attempting sign.
# Prefer scripts/sign_portable.ps1 on Windows (Authenticode / Set-AuthenticodeSignature).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT="${AAS_SIGN_CERT:-}"
PASS="${AAS_SIGN_PASSWORD:-}"
TS="${AAS_SIGN_TIMESTAMP:-http://timestamp.digicert.com}"
DRY_RUN=0
SELF_DEV="${AAS_SIGN_SELF_SIGNED_DEV:-0}"
PATH_ARG=""

usage() {
  cat <<'HELP'
sign_portable.sh — osslsigncode wrapper for portable AI-Agent-Studio EXE(s)

  ./scripts/sign_portable.sh [options] [path]

  path                 EXE or directory (default: dist/AI-Agent-Studio/*.exe)
  --cert <pfx>         PKCS#12 file (or AAS_SIGN_CERT)
  --password <str>     PFX password (or AAS_SIGN_PASSWORD)
  --timestamp <url>    Timestamp URL (or AAS_SIGN_TIMESTAMP)
  --self-signed-dev    DEV ONLY — not for distribution trust
  --dry-run            Print plan; do not sign
  --help               This text

Skips gracefully (exit 0) when osslsigncode or cert is missing.
On Windows prefer: .\scripts\sign_portable.ps1
See docs/CODE_SIGNING.md
HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --self-signed-dev) SELF_DEV=1; shift ;;
    --cert) CERT="${2:-}"; shift 2 ;;
    --password) PASS="${2:-}"; shift 2 ;;
    --timestamp) TS="${2:-}"; shift 2 ;;
    --) shift; break ;;
    -*)
      echo "sign_portable: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *) PATH_ARG="$1"; shift ;;
  esac
done

if [[ "${AAS_SIGN_SKIP:-}" == "1" ]]; then
  echo "sign_portable: AAS_SIGN_SKIP=1 — skipping."
  exit 0
fi

collect_targets() {
  local base="$1"
  if [[ -z "$base" ]]; then
    base="$ROOT/dist/AI-Agent-Studio"
  elif [[ "$base" != /* ]]; then
    base="$ROOT/$base"
  fi
  if [[ -d "$base" ]]; then
    # shellcheck disable=SC2010
    ls -1 "$base"/*.exe 2>/dev/null || true
  elif [[ -f "$base" ]]; then
    echo "$base"
  fi
}

mapfile -t TARGETS < <(collect_targets "$PATH_ARG" | sed '/^$/d')

echo "sign_portable: targets (${#TARGETS[@]}):"
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "  (none)"
else
  for t in "${TARGETS[@]}"; do echo "  - $t"; done
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "sign_portable: dry-run — would sign with cert='${CERT:-}' timestamp='$TS' self_signed_dev=$SELF_DEV"
  if [[ ${#TARGETS[@]} -eq 0 ]]; then
    echo "sign_portable: dry-run note — no EXE targets; live run would skip."
  fi
  if [[ -z "$CERT" ]]; then
    echo "sign_portable: dry-run note — no cert set (AAS_SIGN_CERT / --cert); live run would skip."
  fi
  if ! command -v osslsigncode >/dev/null 2>&1; then
    echo "sign_portable: dry-run note — osslsigncode not on PATH; live run would skip."
  fi
  exit 0
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "sign_portable: no EXE targets under dist/AI-Agent-Studio (or path) — skipping."
  exit 0
fi

if [[ -z "$CERT" ]]; then
  echo "sign_portable: no AAS_SIGN_CERT / --cert — skipping (unsigned build is OK for local use)."
  echo "  See docs/CODE_SIGNING.md to sign for distribution."
  exit 0
fi

if [[ ! -f "$CERT" ]]; then
  echo "sign_portable: cert file not found: $CERT — skipping."
  exit 0
fi

if ! command -v osslsigncode >/dev/null 2>&1; then
  echo "sign_portable: osslsigncode not found on PATH — skipping."
  echo "  Install: https://github.com/mtrojnar/osslsigncode  (or use sign_portable.ps1 on Windows)"
  exit 0
fi

if [[ "$SELF_DEV" == "1" ]]; then
  echo "WARNING: AAS_SIGN_SELF_SIGNED_DEV / --self-signed-dev — DEV ONLY. Do NOT distribute as trusted." >&2
fi

failed=0
for exe in "${TARGETS[@]}"; do
  out="${exe}.signed"
  echo "sign_portable: signing $exe ..."
  args=(sign -pkcs12 "$CERT" -n "AI Agent Studio" -i "https://github.com/agarwal9316-jpg/AI-Agent-Studio" -t "$TS" -in "$exe" -out "$out")
  if [[ -n "$PASS" ]]; then
    args=(sign -pkcs12 "$CERT" -pass "$PASS" -n "AI Agent Studio" -i "https://github.com/agarwal9316-jpg/AI-Agent-Studio" -t "$TS" -in "$exe" -out "$out")
  fi
  if osslsigncode "${args[@]}"; then
    mv -f "$out" "$exe"
    echo "  OK — verify: osslsigncode verify -in \"$exe\""
  else
    echo "  ERROR: osslsigncode failed for $exe" >&2
    rm -f "$out"
    failed=$((failed + 1))
  fi
done

if [[ "$failed" -gt 0 ]]; then
  echo "sign_portable: $failed file(s) failed to sign." >&2
  exit 1
fi

echo "sign_portable: done."
exit 0
