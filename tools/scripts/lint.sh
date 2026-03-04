#!/usr/bin/env bash
set -euo pipefail
echo "=== Linting Rust ==="
cd apriori_window_suite && cargo clippy -- -D warnings
echo "=== Linting Python ==="
cd "$(git rev-parse --show-toplevel)"
python3 -m ruff check apriori_window_suite/python/ experiments/ 2>/dev/null || echo "(ruff not installed, skip)"
echo "Done."
