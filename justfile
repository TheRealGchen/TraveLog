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

# Install the toolchain if missing (Node 24, pnpm, uv, Docker), then the project dependencies
setup:
    ./scripts/install-tools.sh
    PATH="$HOME/.local/bin:$PATH" just install

# Install Python and Node dependencies
install:
    cd {{api}} && uv sync
    pnpm install

# Start MongoDB in Docker, reachable only from this machine, with data in a named volume
mongo docker="docker":
    {{docker}} start travel-mongo 2>/dev/null || {{docker}} run -d --name travel-mongo \
        --restart unless-stopped -p 127.0.0.1:27017:27017 -v travel-mongo-data:/data/db mongo:8

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

# Production build of the web app (bakes in API_URL and API_TOKEN from .env)
build:
    pnpm --filter @travel/web build

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

# Set up this clone on a fresh Ubuntu/Debian node: services, nginx, and automatic HTTPS
provision domain email:
    ./deploy/provision.sh {{domain}} {{email}}

# Update a provisioned node: pull, install, rebuild, restart, and check the services are up
deploy:
    @systemctl cat travel-api.service >/dev/null 2>&1 || { echo "error: this node isn't provisioned yet (no travel-api service). Run: just provision <domain> <email>" >&2; exit 1; }
    git pull --ff-only
    just install
    just build
    $([ "$(id -u)" = 0 ] || echo sudo -n) systemctl restart travel-api travel-web
    @for i in $(seq 1 30); do \
        curl -fsS -o /dev/null http://127.0.0.1:{{api_port}}/llms.txt && curl -fsS -o /dev/null http://127.0.0.1:{{web_port}}/ && break; \
        if [ "$i" = 30 ]; then echo "error: services didn't come up within 30s; check: just logs" >&2; exit 1; fi; \
        sleep 1; \
    done
    @echo "Deployed $(git rev-parse --short HEAD); the API and web app are responding."

# Follow the production service logs
logs:
    journalctl -u travel-api -u travel-web -f
