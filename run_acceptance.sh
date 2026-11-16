#!/bin/bash
# The launcher owns a fresh scope before any runtime or server starts.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/acceptance_launcher.py"
