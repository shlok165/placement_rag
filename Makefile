COMPOSE ?= docker compose
TEST = $(COMPOSE) run --rm test

.PHONY: up down test lint migrate seed eval eval-cross eval-blind eval-live bench e2e backup restore

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
	$(TEST) sh -c "alembic upgrade head && python -m evals.retrieval && python -m evals.taste && python -m evals.agent"

eval-cross: ## Cross-encoder experiment on the development half (downloads the model)
	$(COMPOSE) build test
	$(COMPOSE) run --rm -e HF_HUB_OFFLINE=0 test sh -c "alembic upgrade head && python -m evals.retrieval --cross"

eval-blind: ## The blind set, once per release: make eval-blind RELEASE=v1.0.0
	$(COMPOSE) build test
	$(COMPOSE) run --rm -e HF_HUB_OFFLINE=0 test sh -c "alembic upgrade head && python -m evals.retrieval --blind --release $(RELEASE)"

eval-live: ## Capped live agent eval. Prints the expected calls first
	$(COMPOSE) build test
	TEST_LLM_MODE=live $(TEST) sh -c "alembic upgrade head && python -m evals.agent --live"

bench: ## Scale benchmark at 1k, 10k and 50k postings in a scratch database (about 15 minutes)
	$(COMPOSE) build test
	$(COMPOSE) run --rm test sh -c "alembic upgrade head && python -m evals.bench"

e2e: ## Browser tests against the running stack
	$(COMPOSE) --profile e2e run --rm e2e

backup: ## Dump the database and raw files into ./backups
	sh scripts/backup.sh

restore: ## Restore from a backup: make restore FROM=backups/<name>
	sh scripts/restore.sh $(FROM)
