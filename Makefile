.PHONY: help up down test test-e2e lint typecheck install install-dev clean

# Default target
help:
	@echo "Available targets:"
	@echo "  up                - Start Docker services (Postgres + GROBID)"
	@echo "  down              - Stop Docker services"
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
	@echo "Waiting for services to be ready..."
	@timeout 120 sh -c 'until curl -fsS http://localhost:8070/api/isalive >/dev/null; do sleep 2; done' || \
		(echo "Services did not become ready in time" && exit 1)
	@echo "Services are ready!"

down:
	docker compose down

logs:
	docker compose logs -f

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
	uv run python -m mypy retrieval/

# Installation
install:
	uv sync

install-dev:
	uv sync --group dev

# Cleanup
clean:
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf *.egg-info/
	rm -rf dist/
	rm -rf build/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
