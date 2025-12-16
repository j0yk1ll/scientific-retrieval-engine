.PHONY: help up down logs migrate test test-e2e lint typecheck install install-dev clean

# Default target
help:
	@echo "Available targets:"
	@echo "  up                - Start Docker services (Postgres + GROBID)"
	@echo "  down              - Stop Docker services"
	@echo "  logs              - Tail Docker service logs"
	@echo "  migrate           - Run database migrations to latest"
	@echo "  migrate-downgrade - Rollback last migration"
	@echo "  migrate-history   - Show migration history"
	@echo "  migrate-current   - Show current migration version"
	@echo "  test              - Run all tests"
	@echo "  test-e2e          - Run E2E tests (requires Docker services)"
	@echo "  lint              - Run ruff linter"
	@echo "  typecheck         - Run mypy type checker"
	@echo "  install           - Install runtime dependencies"
	@echo "  install-dev       - Install dev dependencies"
	@echo "  clean             - Remove generated files and caches"

# Docker targets
up:
	docker compose up -d
	@echo "Waiting for services to become healthy..."
	@timeout 120 sh -c 'until docker compose ps | grep -q "healthy"; do sleep 2; done' || \
		(echo "Services did not become healthy in time" && exit 1)
	@echo "Services are ready!"

down:
	docker compose down

logs:
	docker compose logs -f

# Database
migrate:
	RETRIEVAL_DB_DSN="postgresql://retrieval:retrieval@localhost:5432/retrieval" \
		uv run alembic upgrade head

migrate-downgrade:
	RETRIEVAL_DB_DSN="postgresql://retrieval:retrieval@localhost:5432/retrieval" \
		uv run alembic downgrade -1

migrate-history:
	RETRIEVAL_DB_DSN="postgresql://retrieval:retrieval@localhost:5432/retrieval" \
		uv run alembic history

migrate-current:
	RETRIEVAL_DB_DSN="postgresql://retrieval:retrieval@localhost:5432/retrieval" \
		uv run alembic current

# Testing
test:
	uv run pytest tests/

test-unit:
	uv run pytest tests/unit/

test-integration:
	uv run pytest tests/integration/ -m integration

test-e2e:
	RETRIEVAL_DB_DSN="postgresql://retrieval:retrieval@localhost:5432/retrieval" \
        RETRIEVAL_DATA_DIR="./data" \
        RETRIEVAL_INDEX_DIR="./index" \
        RETRIEVAL_GROBID_URL="http://localhost:8070" \
        RETRIEVAL_UNPAYWALL_EMAIL="test@example.com" \
                uv run pytest tests/integration/test_e2e_real_services_and_chromadb.py -v -s

# Code quality
lint:
	uv run ruff check retrieval/ tests/

lint-fix:
	uv run ruff check --fix retrieval/ tests/

typecheck:
	uv run mypy retrieval/

# Installation
install:
	uv sync

install-dev:
	uv sync --group dev

install-tests:
	uv sync --group tests

install-all:
	uv sync --all-groups

# Cleanup
clean:
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf *.egg-info/
	rm -rf dist/
	rm -rf build/
	rm -rf data/
	rm -rf index/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
