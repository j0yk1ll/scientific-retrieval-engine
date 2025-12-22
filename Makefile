.PHONY: help up down test test-unit test-integration lint lint-fix typecheck install install-dev clean

# Default target
help:
	@echo "Available targets:"
	@echo "  up                - Start Docker services"
	@echo "  down              - Stop Docker services"
	@echo "  test              - Run all tests"
	@echo "  test-unit         - Run unit tests"
	@echo "  test-integration  - Run integration tests"
	@echo "  lint              - Run ruff linter"
	@echo "  lint-fix          - Run ruff linter with auto-fix"
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

# Code quality
lint:
	uv run ruff check literature_retrieval_engine/ tests/

lint-fix:
	uv run ruff check --fix literature_retrieval_engine/ tests/

typecheck:
	uv run python -m mypy literature_retrieval_engine/

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
