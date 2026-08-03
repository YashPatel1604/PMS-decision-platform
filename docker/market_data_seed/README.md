# Canonical market-data CSVs for Docker (prices, dividends, benchmarks, successors).
# Refresh does NOT load these — run scripts/windows/load-market-analysis.ps1
# (or: docker compose exec api uv run pms-platform import-market-data
#      && docker compose exec api uv run pms-platform analyze-episodes).
#
# To refresh from OneDrive 05_External_Data on the host, set in .env:
#   EXTERNAL_DATA_DIR=C:/Users/.../PMS-Decision-Platform/05_External_Data
