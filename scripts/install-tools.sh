#!/usr/bin/env bash
# Install the toolchain this repo needs, skipping anything already present:
#   Node.js 24+ (NodeSource), pnpm 10, uv (which installs the Python version the API pins),
#   and Docker (for MongoDB and the API tests).
# Installing needs Ubuntu/Debian (apt) and sudo; on other systems it says what to install.
# Used by `just setup` and by `just provision`.
set -euo pipefail

step() { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok() { printf '    %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

has_apt() { command -v apt-get >/dev/null; }
need_apt() { has_apt || fail "$1 is missing; install it manually ($2), then re-run"; }

# Run with sudo unless already root.
as_root() { if [[ "$(id -u)" == 0 ]]; then "$@"; else sudo "$@"; fi; }

# The installers below are fetched with curl.
if ! command -v curl >/dev/null; then
  need_apt "curl" "your package manager"
  as_root apt-get update -qq
  as_root apt-get install -y -qq curl ca-certificates
fi

step "Node.js 24+"
if node --version 2>/dev/null | grep -qE '^v(2[4-9]|[3-9][0-9])\.'; then
  ok "found $(node --version)"
else
  need_apt "Node.js 24+" "https://nodejs.org"
  curl -fsSL https://deb.nodesource.com/setup_24.x | as_root bash -
  as_root apt-get install -y -qq nodejs >/dev/null
  ok "installed $(node --version)"
fi

step "pnpm 10"
if command -v pnpm >/dev/null; then
  ok "found $(pnpm --version)"
else
  # Global npm installs need root only when Node lives in a system directory (not nvm).
  if [[ -w "$(npm prefix -g)" ]]; then
    npm install -g pnpm@10
  else
    as_root npm install -g pnpm@10
  fi
  ok "installed $(pnpm --version)"
fi

step "uv"
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null; then
  ok "found $(uv --version)"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ok "installed $(uv --version) (in ~/.local/bin; open a new shell if it isn't on your PATH)"
fi

step "Docker"
if command -v docker >/dev/null; then
  ok "found $(docker --version)"
else
  need_apt "Docker" "https://docs.docker.com/engine/install/"
  as_root apt-get update -qq
  as_root apt-get install -y -qq docker.io >/dev/null
  as_root systemctl enable --now docker 2>/dev/null || true
  if [[ "$(id -u)" != 0 ]]; then
    as_root usermod -aG docker "$(id -un)"
    ok "added $(id -un) to the docker group; log out and back in to use docker without sudo"
  fi
  ok "installed $(docker --version)"
fi
