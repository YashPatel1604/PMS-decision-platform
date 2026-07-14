.PHONY: install dev test lint typecheck format docker-up docker-down

install:
	uv sync

dev:
	uv run uvicorn pms_platform.api.main:app --reload

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

docker-down:
	docker compose down
