#!/usr/bin/env bash
set -euo pipefail
echo "=== Formatting Rust ==="
cd apriori_window_suite && cargo fmt
echo "=== Formatting Python ==="
cd "$(git rev-parse --show-toplevel)"
python3 -m ruff format apriori_window_suite/python/ experiments/ comparative_methods/ 2>/dev/null || echo "(ruff not installed, skip)"
echo "Done."
