.DEFAULT_GOAL := help
COMPOSE ?= docker compose
PYTEST  := uv run pytest

.PHONY: help install fmt lint typecheck test-unit test-integration test-e2e infra up down logs demo

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install the locked dependency set (runtime + dev)
	uv sync --locked

fmt: ## Format code and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## Run pyright in strict mode
	uv run pyright

test-unit: ## Fast tests on in-memory fakes (no I/O)
	$(PYTEST) -m unit

infra: ## Start only Postgres and RabbitMQ (for integration tests)
	$(COMPOSE) up -d --wait postgres rabbitmq

test-integration: infra ## Tests against real Postgres/RabbitMQ from compose
	$(PYTEST) -m integration

test-e2e: up ## Black-box tests against the whole compose stack
	$(PYTEST) -m e2e

up: ## Build and start the whole stack, waiting for health checks
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack and drop volumes
	$(COMPOSE) down -v --remove-orphans

logs: ## Follow logs of all services
	$(COMPOSE) logs -f

demo: up ## Run the curl walkthrough: create, replay, 409, GET, retry -> DLQ
	./scripts/demo.sh
