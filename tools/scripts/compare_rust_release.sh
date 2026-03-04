#!/usr/bin/env bash
set -euo pipefail

# Compare original and suite under identical RELEASE conditions.
# Usage:
#   ./experiments/compare_rust_release.sh [N]
# N: repeat count (default: 3)

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
N="${1:-3}"

ORIG_BIN="$ROOT_DIR/apriori_window_original/target/release/new_apriori_window"
SUITE_BIN="$ROOT_DIR/apriori_window_suite/target/release/apriori_window_suite"
ORIG_SETTINGS="$ROOT_DIR/apriori_window_original/data/settings.json"
SUITE_SETTINGS="$ROOT_DIR/apriori_window_suite/data/settings.json"

echo "[info] building release binaries..."
cargo build --release --manifest-path "$ROOT_DIR/apriori_window_original/Cargo.toml" >/dev/null
cargo build --release --manifest-path "$ROOT_DIR/apriori_window_suite/Cargo.toml" >/dev/null

echo "[info] comparing release runs (N=$N)"
echo "[info] original settings: $ORIG_SETTINGS"
echo "[info] suite settings:    $SUITE_SETTINGS"
echo

for i in $(seq 1 "$N"); do
  echo "[run $i/$N] original"
  "$ORIG_BIN" "$ORIG_SETTINGS" | rg "Elapsed time|Wrote output"
  echo "[run $i/$N] suite phase1"
  "$SUITE_BIN" phase1 "$SUITE_SETTINGS" | rg "Elapsed time|パターン出力"
  echo
done

echo "[done] release-only comparison finished."
