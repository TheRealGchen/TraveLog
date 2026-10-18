#!/usr/bin/env bash
# Provision this repo on a fresh Ubuntu/Debian node: dependencies, MongoDB in Docker, the API
# and web app as systemd services, nginx as the reverse proxy, and HTTPS from Let's Encrypt.
#
# Usage (from the cloned repo, as a regular user with sudo): just provision <domain> <email>
# The domain's DNS must already point at this node, and ports 80 and 443 must be reachable.
# Safe to re-run: it updates what is there and keeps the existing certificate and API token.
set -euo pipefail

DOMAIN="${1:?usage: just provision <domain> <email>}"
EMAIL="${2:?usage: just provision <domain> <email>}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3001}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(id -un)"
ENV_FILE="$REPO/.env"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# [[ "$(id -u)" != 0 ]] || fail "run as a regular user with sudo, not root (the services run as you)"
command -v apt-get >/dev/null || fail "this script supports Ubuntu/Debian (apt) only"
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || fail "'$DOMAIN' doesn't look like a domain name"
[[ "$EMAIL" == *@*.* ]] || fail "'$EMAIL' doesn't look like an email address"

# Replace __PLACEHOLDERS__ in a template and install it with sudo.
render() {
  local template="$1" dest="$2"
  sed -e "s|__DOMAIN__|$DOMAIN|g" \
      -e "s|__REPO__|$REPO|g" \
      -e "s|__USER__|$RUN_USER|g" \
      -e "s|__NODE__|$(command -v node)|g" \
      -e "s|__API_PORT__|$API_PORT|g" \
      -e "s|__WEB_PORT__|$WEB_PORT|g" \
      "$template" | sudo tee "$dest" >/dev/null
}

# Set KEY=VALUE in .env, replacing an existing line or appending one.
set_env() {
  local key="$1" value="$2"
  if grep -q "^$key=" "$ENV_FILE"; then
    sed -i "s|^$key=.*|$key=$value|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

step "Installing system packages (nginx, certbot)"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  nginx certbot python3-certbot-nginx curl ca-certificates openssl git

step "Installing the toolchain (Node.js, pnpm, uv, Docker)"
"$REPO/scripts/install-tools.sh"
export PATH="$HOME/.local/bin:$PATH"

step "Starting MongoDB in Docker (localhost only)"
sudo systemctl enable --now docker
(cd "$REPO" && just mongo "sudo docker")

step "Configuring $ENV_FILE"
[[ -f "$ENV_FILE" ]] || cp "$REPO/.env.example" "$ENV_FILE"
chmod 600 "$ENV_FILE"
current_token="$(grep -E '^API_TOKEN=' "$ENV_FILE" | cut -d= -f2- || true)"
if [[ -z "$current_token" || "$current_token" == "change-me" ]]; then
  set_env API_TOKEN "$(openssl rand -hex 32)"
  echo "Generated a new API_TOKEN."
fi
set_env MONGODB_URI "mongodb://127.0.0.1:27017"
set_env API_URL "https://$DOMAIN"
set_env WEB_ORIGIN "https://$DOMAIN"

step "Installing dependencies and building the web app"
# Run in a clean environment so the build reads the .env written above, not values that
# `just` loaded from the old .env before this script started.
clean_env=(env -u API_URL -u API_TOKEN -u WEB_ORIGIN -u MONGODB_URI -u MONGODB_DB -u LINK_PREVIEWS)
(cd "$REPO" && "${clean_env[@]}" just install && "${clean_env[@]}" just build)

step "Installing systemd services (travel-api, travel-web)"
render "$REPO/deploy/systemd/travel-api.service" /etc/systemd/system/travel-api.service
render "$REPO/deploy/systemd/travel-web.service" /etc/systemd/system/travel-web.service
sudo systemctl daemon-reload
sudo systemctl enable travel-api travel-web
sudo systemctl restart travel-api travel-web

step "Configuring nginx for $DOMAIN"
sudo install -m 644 "$REPO/deploy/nginx/travel-planner-proxy.conf" \
  /etc/nginx/snippets/travel-planner-proxy.conf
render "$REPO/deploy/nginx/travel-planner.conf" /etc/nginx/sites-available/travel-planner
sudo ln -sf /etc/nginx/sites-available/travel-planner /etc/nginx/sites-enabled/travel-planner
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  step "Opening ports 80 and 443 in ufw"
  sudo ufw allow 'Nginx Full'
fi

step "Getting an HTTPS certificate from Let's Encrypt"
# Issues a certificate (or reuses a valid one), adds HTTPS to the nginx site, and redirects
# HTTP to HTTPS. The certbot package's systemd timer renews it automatically.
sudo certbot --nginx -d "$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive \
  --redirect --keep-until-expiring
sudo systemctl enable --now certbot.timer 2>/dev/null || true

step "Checking the deployment"
for _ in $(seq 1 30); do
  if curl -fsS "https://$DOMAIN/llms.txt" >/dev/null 2>&1 && curl -fsS "https://$DOMAIN/" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS -o /dev/null -w "web  https://$DOMAIN/          -> %{http_code}\n" "https://$DOMAIN/" \
  || fail "the web app isn't responding over HTTPS; check: just logs"
curl -fsS -o /dev/null -w "api  https://$DOMAIN/llms.txt  -> %{http_code}\n" "https://$DOMAIN/llms.txt" \
  || fail "the API isn't responding over HTTPS; check: just logs"
systemctl list-timers certbot.timer --no-pager | head -2 || true

cat <<EOF

Done. Open https://$DOMAIN
Agents use the API at https://$DOMAIN/v1 with the API_TOKEN from $ENV_FILE.
Note: the web app is not password-protected, and the API token is visible in its JavaScript.
Update later with: just deploy
EOF
