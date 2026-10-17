.DEFAULT_GOAL := help
SCENARIO ?= pool-exhaustion
EVALS ?=

.PHONY: help up down logs db api web smoke indexes seed inject reset catalogue test eval lint fmt mcp

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  make %-8s %s\n", $$1, $$2}'

up: ## Start FalkorDB + API in Docker (browser on :3000, API on :8000)
	docker compose up -d --build

down: ## Stop containers (graph data is kept in the falkordb_data volume)
	docker compose down

logs: ## Follow container logs
	docker compose logs -f

db: ## Start only FalkorDB (for running the API and tests on the host)
	docker compose up -d falkordb

api: ## Run the API on the host with reload (needs `make db`)
	cd backend && uv run uvicorn pagersage.main:app --reload --port 8000

web: ## Run the Next.js dev server on :3100
	cd frontend && npm run dev

smoke: ## Check every FalkorDB procedure the plan uses (needs `make db`)
	cd backend && uv run python ../scripts/smoke_algos.py

indexes: ## Create missing indexes and unique id constraints (idempotent; needs `make db`)
	cd backend && uv run python -m pagersage.indexes

seed: ## Ingest Kestrel Pay into the graph (task G03)
	cd backend && uv run python -m pagersage.seed

inject: ## Break Kestrel Pay, e.g. make inject SCENARIO=pool-exhaustion (task K7)
	@test -f kestrel-pay/scenarios/inject.py || { echo "make inject is not implemented yet: task K7 (kestrel-pay/PLAN.md)" >&2; exit 2; }
	cd backend && uv run python ../kestrel-pay/scenarios/inject.py $(SCENARIO)

reset: ## Restore the seed graph for a fresh demo run (task G03)
	cd backend && uv run python -m pagersage.seed --reset

catalogue: ## Regenerate docs/cypher.md from backend/queries/ (task G19)
	cd backend && uv run python ../scripts/cypher_catalogue.py

test: ## Run backend and Kestrel Pay tests (needs `make db`)
	cd backend && uv run pytest

eval: ## Scenarios end to end with real Claude calls (costs money; EVALS=redis-down for one) (A12)
	cd backend && uv run python -m evals.scenarios $(EVALS)

lint: ## Lint backend, Kestrel Pay and frontend
	cd backend && uv run ruff check . ../kestrel-pay ../scripts && uv run ruff format --check . ../kestrel-pay ../scripts
	cd frontend && npm run lint

fmt: ## Auto-format backend and Kestrel Pay code
	cd backend && uv run ruff check --fix . ../kestrel-pay ../scripts && uv run ruff format . ../kestrel-pay ../scripts

mcp: ## Run FalkorDB-MCPServer (read-only, stdio) against local FalkorDB
	FALKORDB_HOST=localhost FALKORDB_PORT=6379 FALKORDB_DEFAULT_READONLY=true npx -y @falkordb/mcpserver@1.3.0
