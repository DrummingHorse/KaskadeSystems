#!/usr/bin/env bash
# Reproduce every recorded result: tests, demo, independent receipt check.
# Usage (from the prospektor/ folder):  bash tools/reproduce.sh [python3]
# Needs only Python 3.10+ (standard library). Uses OpenSSL, via the `cryptography`
# package or the `openssl` command, for the independent signature check if present.
# No network access, no downloads, no real funds.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-python3}"
OUT="$(mktemp -d "${TMPDIR:-/tmp}/prospektor-repro-XXXXXX")"

echo "== $("$PY" -c 'import sys; print("Python", sys.version.split()[0])')"
echo "== 1/3 test suite"
"$PY" -m unittest discover -s tests -p "test_*.py"

echo "== 2/3 end-to-end demo (writes $OUT)"
"$PY" -m prospektor demo --out "$OUT" --quiet
tail -n 8 "$OUT/transcript.txt"

echo "== 3/3 independent receipt check (does not import the prospektor package)"
ASSAYER="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["assayer"])' "$OUT/summary.json" 2>/dev/null || true)"
"$PY" tools/verify_receipts.py "$OUT/receipts.jsonl" --events "$OUT/events.jsonl" ${ASSAYER:+--assayer "$ASSAYER"}

echo "== compare with the recorded run"
for f in receipts.jsonl events.jsonl transactions.jsonl; do
  if cmp -s "$OUT/$f" "evidence/demo-run/$f"; then echo "   $f identical to evidence/demo-run/$f"
  else echo "   $f DIFFERS from evidence/demo-run/$f (engine or fixtures changed?)"; fi
done
