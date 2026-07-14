#!/usr/bin/env bash
# Copy editable OneDrive source workbooks into data/raw (read-only copies).
# Source of truth lives outside the repo app folder; data/raw is never edited by hand.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$(cd "$ROOT_DIR/.." && pwd)"

FINAL_MASTER="${ONEDRIVE_FINAL_MASTER:-$PARENT_DIR/02_Final_Master}"
SNAPSHOT_SRC="${ONEDRIVE_SNAPSHOTS:-$PARENT_DIR/00_Original_Files/Portfolio_Snapshots}"
RAW_DIR="${RAW_DATA_DIR:-$ROOT_DIR/data/raw}"

# Prefer newest transaction master when present.
if [[ -f "$FINAL_MASTER/TRANSACTIONS_MASTER_V5_HARD_RECON_FIXES.xlsx" ]]; then
  TXN_SRC="$FINAL_MASTER/TRANSACTIONS_MASTER_V5_HARD_RECON_FIXES.xlsx"
elif [[ -f "$FINAL_MASTER/TRANSACTIONS_MASTER_V3_2012_RECONCILIATION_POLICY.xlsx" ]]; then
  TXN_SRC="$FINAL_MASTER/TRANSACTIONS_MASTER_V3_2012_RECONCILIATION_POLICY.xlsx"
elif [[ -f "$FINAL_MASTER/TRANSACTIONS_MASTER_V2_PRE2021_CORPORATE_ACTIONS.xlsx" ]]; then
  TXN_SRC="$FINAL_MASTER/TRANSACTIONS_MASTER_V2_PRE2021_CORPORATE_ACTIONS.xlsx"
elif [[ -f "$FINAL_MASTER/TRANSACTIONS_MASTER_V2.xlsx" ]]; then
  TXN_SRC="$FINAL_MASTER/TRANSACTIONS_MASTER_V2.xlsx"
else
  TXN_SRC="$FINAL_MASTER/TRANSACTIONS_MASTER_V1.xlsx"
fi
SEC_SRC="$FINAL_MASTER/SECURITY_MASTER_V1.xlsx"

copy_ro() {
  local src="$1"
  local dest="$2"
  if [[ ! -f "$src" ]]; then
    echo "Missing source: $src" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$dest")"
  chmod u+w "$dest" 2>/dev/null || true
  cp "$src" "$dest"
  chmod a-w "$dest"
  echo "  $(basename "$dest")  ←  $src"
}

echo "Syncing OneDrive sources → $RAW_DIR"
echo "  FINAL_MASTER=$FINAL_MASTER"
echo "  SNAPSHOT_SRC=$SNAPSHOT_SRC"

copy_ro "$TXN_SRC" "$RAW_DIR/transactions/MASTER_TRANSACTIONS_V1.xlsx"
copy_ro "$SEC_SRC" "$RAW_DIR/security_master/SECURITY_MASTER_V1.xlsx"

shopt -s nullglob
snap_count=0
for src in "$SNAPSHOT_SRC"/Portfolio_*.xlsx; do
  base="$(basename "$src")"
  # Skip Excel lock/temp files
  if [[ "$base" == ~\$* ]]; then
    continue
  fi
  copy_ro "$src" "$RAW_DIR/portfolio_snapshots/$base"
  snap_count=$((snap_count + 1))
done

if [[ "$snap_count" -eq 0 ]]; then
  echo "No Portfolio_*.xlsx found in $SNAPSHOT_SRC" >&2
  exit 1
fi

echo "Done. Synced 2 masters + $snap_count snapshot workbooks."
echo "Next: make reimport   # or: make sync-import"
