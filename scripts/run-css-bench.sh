#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$ROOT/css-bench/update_vendor.py"
python3 "$ROOT/css-bench/run.py" "$@"
