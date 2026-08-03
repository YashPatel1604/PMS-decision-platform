#!/usr/bin/env bash
# Copy editable OneDrive source workbooks into data/raw (read-only copies).
# Authoritative knowledge base: sibling ../Research (read-only; never written).
# Legacy fallbacks: 02_Final_Master and 00_Original_Files under the project tree.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$(cd "$ROOT_DIR/.." && pwd)"
ONEDRIVE_PERSONAL="$(cd "$PARENT_DIR/.." && pwd)"

RESEARCH_DIR="${RESEARCH_DIR:-$ONEDRIVE_PERSONAL/Research}"
RESEARCH_PORTFOLIO="$RESEARCH_DIR/Portfolio"
RESEARCH_YEARLY="$RESEARCH_PORTFOLIO/Portfolio Yearly"

FINAL_MASTER="${ONEDRIVE_FINAL_MASTER:-$PARENT_DIR/02_Final_Master}"
LEGACY_SNAPSHOT_SRC="$PARENT_DIR/00_Original_Files/Portfolio_Snapshots"
RAW_DIR="${RAW_DATA_DIR:-$ROOT_DIR/data/raw}"

# Prefer Research yearly books, then Research/Portfolio root, then legacy originals.
if [[ -n "${ONEDRIVE_SNAPSHOTS:-}" ]]; then
  SNAPSHOT_SRC="$ONEDRIVE_SNAPSHOTS"
elif [[ -d "$RESEARCH_YEARLY" ]] && compgen -G "$RESEARCH_YEARLY"/Portfolio_*.xlsx > /dev/null; then
  SNAPSHOT_SRC="$RESEARCH_YEARLY"
elif [[ -d "$RESEARCH_PORTFOLIO" ]] && compgen -G "$RESEARCH_PORTFOLIO"/Portfolio_*.xlsx > /dev/null; then
  SNAPSHOT_SRC="$RESEARCH_PORTFOLIO"
else
  SNAPSHOT_SRC="$LEGACY_SNAPSHOT_SRC"
fi

# Prefer newest transaction master when present (Research first, then Final Master).
pick_txn() {
  local name="$1"
  if [[ -f "$RESEARCH_PORTFOLIO/$name" ]]; then
    echo "$RESEARCH_PORTFOLIO/$name"
    return 0
  fi
  if [[ -f "$FINAL_MASTER/$name" ]]; then
    echo "$FINAL_MASTER/$name"
    return 0
  fi
  return 1
}

TXN_SRC=""
for name in \
  TRANSACTIONS_MASTER_V5_HARD_RECON_FIXES.xlsx \
  TRANSACTIONS_MASTER_V3_2012_RECONCILIATION_POLICY.xlsx \
  TRANSACTIONS_MASTER_V2_PRE2021_CORPORATE_ACTIONS.xlsx \
  TRANSACTIONS_MASTER_V2.xlsx \
  TRANSACTIONS_MASTER_V1.xlsx
do
  if TXN_SRC="$(pick_txn "$name")"; then
    break
  fi
done
if [[ -z "$TXN_SRC" ]]; then
  TXN_SRC="$FINAL_MASTER/TRANSACTIONS_MASTER_V1.xlsx"
fi

if [[ -f "$RESEARCH_PORTFOLIO/SECURITY_MASTER_V1.xlsx" ]]; then
  SEC_SRC="$RESEARCH_PORTFOLIO/SECURITY_MASTER_V1.xlsx"
else
  SEC_SRC="$FINAL_MASTER/SECURITY_MASTER_V1.xlsx"
fi

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
echo "  RESEARCH_DIR=$RESEARCH_DIR"
echo "  FINAL_MASTER=$FINAL_MASTER"
echo "  SNAPSHOT_SRC=$SNAPSHOT_SRC"

copy_ro "$TXN_SRC" "$RAW_DIR/transactions/MASTER_TRANSACTIONS_V1.xlsx"
copy_ro "$SEC_SRC" "$RAW_DIR/security_master/SECURITY_MASTER_V1.xlsx"

shopt -s nullglob
snap_count=0

already_synced() {
  local base="$1"
  [[ -f "$RAW_DIR/portfolio_snapshots/$base" ]]
}

sync_snap_dir() {
  local dir="$1"
  [[ -d "$dir" ]] || return 0
  local src base
  for src in "$dir"/Portfolio_*.xlsx; do
    base="$(basename "$src")"
    if [[ "$base" == ~\$* ]]; then
      continue
    fi
    if already_synced "$base"; then
      # Prefer first source in priority order; skip duplicates from later dirs.
      continue
    fi
    copy_ro "$src" "$RAW_DIR/portfolio_snapshots/$base"
    snap_count=$((snap_count + 1))
  done
}

# Clear previous snapshot copies so Research priority is respected on re-sync.
mkdir -p "$RAW_DIR/portfolio_snapshots"
chmod u+w "$RAW_DIR/portfolio_snapshots"/* 2>/dev/null || true
rm -f "$RAW_DIR/portfolio_snapshots"/Portfolio_*.xlsx

sync_snap_dir "$SNAPSHOT_SRC"
# Also pick up root-level Research books (e.g. Portfolio_2026.xlsx) when yearly was primary.
if [[ "$SNAPSHOT_SRC" == "$RESEARCH_YEARLY" ]]; then
  sync_snap_dir "$RESEARCH_PORTFOLIO"
fi

if [[ "$snap_count" -eq 0 ]]; then
  echo "No Portfolio_*.xlsx found in $SNAPSHOT_SRC" >&2
  exit 1
fi

echo "Done. Synced 2 masters + $snap_count snapshot workbooks."
echo "Next: make reimport   # or: make sync-import"
