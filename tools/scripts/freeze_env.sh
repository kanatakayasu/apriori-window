#!/usr/bin/env bash
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel)
echo "=== Freezing Python environment ==="
pip freeze > "$ROOT/requirements.lock"
echo "Saved to requirements.lock"
echo "=== Rust toolchain info ==="
rustc --version
cargo --version
