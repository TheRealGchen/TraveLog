# Common commands. Run `just` to list them.
# Variables from .env (see .env.example) are loaded and exported to every recipe.

set dotenv-load
set export

api := "apps/api"
web := "apps/web"
web_port := env("WEB_PORT", "3001")
api_port := env("API_PORT", "8000")

# List the recipes
default:
    @just --list --unsorted

# Install Python and Node dependencies
install:
    cd {{api}} && uv sync
    pnpm install

# Start a local MongoDB in Docker (alternative to Atlas)
mongo:
    docker start travel-mongo 2>/dev/null || docker run -d --name travel-mongo -p 27017:27017 mongo:8

# Run the API and the web app together (Ctrl-C stops both)
dev:
    #!/usr/bin/env bash
    trap 'kill 0' EXIT
    just dev-api &
    just dev-web &
    wait

# Run the API with reload
dev-api:
    cd {{api}} && uv run uvicorn travel_api.main:create_app --factory --reload --port {{api_port}}

# Run the web app
dev-web:
    cd {{web}} && pnpm exec next dev --port {{web_port}}

# Lint and type-check everything
lint:
    cd {{api}} && uv run ruff check && uv run ruff format --check && uv run ty check
    pnpm --filter @travel/web lint
    pnpm --filter @travel/web typecheck

# Everything CI runs (except e2e)
test: lint check-openapi check-client test-api test-web

# API tests (needs Docker for the throwaway MongoDB)
test-api:
    cd {{api}} && uv run pytest

# Frontend unit tests
test-web:
    pnpm --filter @travel/web test

# Export the API spec to openapi.json
openapi:
    cd {{api}} && uv run python scripts/export_openapi.py ../../openapi.json

# Fail if openapi.json is out of date
check-openapi:
    cd {{api}} && uv run python scripts/export_openapi.py --check ../../openapi.json

# Regenerate the TypeScript client from openapi.json
gen-client:
    pnpm --filter @travel/client gen

# Fail if the generated client is out of date
check-client:
    pnpm --filter @travel/client check

# Playwright smoke test (starts MongoDB, its own API, and a production web build)
e2e: mongo
    pnpm --filter @travel/web e2e
