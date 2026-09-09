#!/usr/bin/env bash
# Point DailyEditFiles at canonical names the app expects (no duplicate workbooks).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${DAILY_EDIT_DIR:-$ROOT/../DailyEditFiles}"
mkdir -p "$DIR"
cd "$DIR"

link_newest() {
  local pattern="$1" dest="$2"
  local src
  src="$(ls -t $pattern 2>/dev/null | head -1 || true)"
  if [[ -z "$src" ]]; then
    echo "skip $dest (no match for $pattern)"
    return
  fi
  if [[ "$src" == "$dest" ]]; then
    echo "ok   $dest"
    return
  fi
  rm -f "$dest"
  cp -p "$src" "$dest"
  echo "sync $src -> $dest"
}

link_newest '*[Pp][Mm][Ss]*[Cc]lient*.xlsx' PMS_ClientPortfolio.xlsx
link_newest '*[Cc]hart*.xlsx' Charts.xlsx
link_newest '*[Ss][Cc][Aa]*[Ll][Ll][Pp]*.xlsx' 'SCA_LLP Stock Holding.xlsx'
link_newest '*[Pp]ivot*.xlsx' PivotPoints.xlsx

echo "DailyEditFiles at: $DIR"
ls -la PMS_ClientPortfolio.xlsx Charts.xlsx 'SCA_LLP Stock Holding.xlsx' PivotPoints.xlsx 2>/dev/null || true
