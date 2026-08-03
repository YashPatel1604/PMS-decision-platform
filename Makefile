.PHONY: install dev dev-api dev-ui test lint typecheck format docker-up docker-up-all docker-down import-all portfolio-on reconcile sync-raw reimport sync-import sync-external import-market-data market-data-coverage analyze-episodes refresh-live-quotes

install:
	uv sync

dev-api:
	uv run uvicorn pms_platform.api.main:app --reload --host 127.0.0.1 --port 8000

dev-ui:
	cd app && pnpm dev

dev: dev-api

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

format:
	uv run ruff format .

docker-up:
	docker compose up -d postgres

docker-up-all:
	docker compose up -d --build

docker-down:
	docker compose down

import-all:
	uv run pms-platform import-all

portfolio-on:
	uv run pms-platform portfolio-on --date $(DATE)

reconcile:
	uv run pms-platform reconcile-snapshots

# Copy OneDrive masters/snapshots → data/raw (read-only copies)
sync-raw:
	bash scripts/sync_raw_from_onedrive.sh

# Clear DB imports and reload from data/raw (needed after sync; checksum gates skip unchanged files)
reimport:
	uv run python scripts/reimport_from_raw.py

# One-shot: sync from OneDrive then rebuild DB + reconciliation report
sync-import: sync-raw reimport

# Copy OneDrive external market-data CSVs → data/external
sync-external:
	bash scripts/sync_external_from_onedrive.sh

import-market-data:
	uv run pms-platform import-market-data

market-data-coverage:
	uv run pms-platform market-data-coverage

analyze-episodes:
	uv run pms-platform analyze-episodes

refresh-live-quotes:
	uv run pms-platform refresh-live-quotes
