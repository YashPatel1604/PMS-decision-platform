#!/usr/bin/env bash
# Copy OneDrive external market-data CSVs into data/external (read-only copies).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$(cd "$ROOT_DIR/.." && pwd)"

EXTERNAL_SRC="${ONEDRIVE_EXTERNAL_DATA:-$PARENT_DIR/05_External_Data}"
EXTERNAL_DIR="${EXTERNAL_DATA_DIR:-$ROOT_DIR/data/external}"

copy_ro() {
  local src="$1"
  local dest="$2"
  if [[ ! -f "$src" ]]; then
    echo "  skip missing: $src"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  chmod u+w "$dest" 2>/dev/null || true
  cp "$src" "$dest"
  chmod a-w "$dest"
  echo "  $(basename "$dest")  ←  $src"
}

echo "Syncing OneDrive external data → $EXTERNAL_DIR"
echo "  EXTERNAL_SRC=$EXTERNAL_SRC"

copy_ro "$EXTERNAL_SRC/prices/daily_prices.csv" "$EXTERNAL_DIR/prices/daily_prices.csv"
copy_ro "$EXTERNAL_SRC/dividends/dividends.csv" "$EXTERNAL_DIR/dividends/dividends.csv"
copy_ro "$EXTERNAL_SRC/benchmarks/benchmark_tri.csv" "$EXTERNAL_DIR/benchmarks/benchmark_tri.csv"
copy_ro "$EXTERNAL_SRC/symbol_maps/security_successors.csv" "$EXTERNAL_DIR/symbol_maps/security_successors.csv"

echo "Done. Next: make import-market-data"
