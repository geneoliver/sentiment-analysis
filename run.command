#!/bin/bash
# Double-clickable convenience launcher (Finder: "Open" or `chmod +x` then double-click).
# The real interface is the CLI (`python -m src.cli ...`) — this just saves
# opening a terminal and cd-ing in for the common case of running everything
# against the latest downloaded exports.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

source .venv/bin/activate

LATEST_AMEX=$(ls -t inputs/amex_*.csv 2>/dev/null | head -n1 || true)
LATEST_CHECKING=$(ls -t inputs/checking_*.csv 2>/dev/null | head -n1 || true)

if [ -z "$LATEST_AMEX" ] || [ -z "$LATEST_CHECKING" ]; then
  echo "Drop your latest exports into inputs/ first, named like:"
  echo "  inputs/amex_2026-06.csv"
  echo "  inputs/checking_2026-06.csv"
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

echo "Using:"
echo "  Amex:     $LATEST_AMEX"
echo "  Checking: $LATEST_CHECKING"

python -m src.cli run --amex "$LATEST_AMEX" --checking "$LATEST_CHECKING"

echo
echo "Done. Check outputs/ for the workbook, and outputs/<run-id>/review.csv for anything worth a manual look."
read -n 1 -s -r -p "Press any key to close..."
