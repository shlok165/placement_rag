COMPOSE ?= docker compose
TEST = $(COMPOSE) run --rm test

.PHONY: up down test lint migrate seed eval eval-live e2e backup restore

up: ## Build and start everything
	$(COMPOSE) up --build -d --wait

down: ## Stop everything, keep data
	$(COMPOSE) down

test: ## Backend and frontend tests, in mock mode
	$(COMPOSE) build test frontend-test
	$(TEST) pytest
	$(COMPOSE) run --rm --no-deps frontend-test npm test

lint: ## Linters and type checks
	$(COMPOSE) build test frontend-test
	$(COMPOSE) run --rm --no-deps test sh -c "ruff check . && ruff format --check . && mypy app"
	$(COMPOSE) run --rm --no-deps frontend-test sh -c "npm run lint && npm run typecheck"

migrate: ## Apply database migrations
	$(COMPOSE) run --rm backend alembic upgrade head

seed: ## Load demo accounts and synthetic postings
	$(COMPOSE) run --rm -e SEED_DEMO=1 backend python -m app.cli bootstrap

eval: ## Everything that is free: retrieval and offline agent evals
	$(COMPOSE) build test
	$(TEST) sh -c "alembic upgrade head && python -m evals.retrieval"

backup: ## Dump the database and raw files into ./backups
	sh scripts/backup.sh

restore: ## Restore from a backup: make restore FROM=backups/<name>
	sh scripts/restore.sh $(FROM)
