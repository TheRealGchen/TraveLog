# Common commands. Variables from .env (see .env.example) are exported to every recipe.
-include .env
export

API := apps/api
WEB := apps/web
CLIENT := packages/client
WEB_PORT ?= 3001
API_PORT ?= 8000

.PHONY: install dev dev-api dev-web mongo test test-api test-web lint openapi check-openapi \
	gen-client check-client e2e

install: ## Install Python and Node dependencies
	cd $(API) && uv sync
	pnpm install

mongo: ## Start a local MongoDB in Docker (alternative to Atlas)
	docker start travel-mongo 2>/dev/null || docker run -d --name travel-mongo -p 27017:27017 mongo:8

dev: ## Run the API and the web app together
	$(MAKE) -j2 dev-api dev-web

dev-api:
	cd $(API) && uv run uvicorn travel_api.main:create_app --factory --reload --port $(API_PORT)

dev-web:
	cd $(WEB) && pnpm exec next dev --port $(WEB_PORT)

lint: ## Lint and type-check everything
	cd $(API) && uv run ruff check && uv run ruff format --check && uv run ty check
	pnpm --filter @travel/web lint
	pnpm --filter @travel/web typecheck

test: lint check-openapi check-client test-api test-web ## Everything CI runs (except e2e)

test-api: ## API tests (needs Docker for the throwaway MongoDB)
	cd $(API) && uv run pytest

test-web: ## Frontend unit tests
	pnpm --filter @travel/web test

openapi: ## Export the API spec to openapi.json
	cd $(API) && uv run python scripts/export_openapi.py ../../openapi.json

check-openapi: ## Fail if openapi.json is out of date
	cd $(API) && uv run python scripts/export_openapi.py --check ../../openapi.json

gen-client: ## Regenerate the TypeScript client from openapi.json
	pnpm --filter @travel/client gen

check-client: ## Fail if the generated client is out of date
	pnpm --filter @travel/client check

e2e: mongo ## Playwright smoke test (starts MongoDB, the API, and the web app)
	pnpm --filter @travel/web e2e
