#!/usr/bin/env bash
# ===========================================================================
# One-shot deploy for a fresh Ubuntu VM (e.g. Oracle Cloud Always Free ARM).
#
#   Run this from inside the cloned repo directory:
#       bash deploy/setup.sh [SITE_ADDRESS]
#
#   SITE_ADDRESS is optional — if omitted, we auto-detect the VM's public IP
#   and use "<ip>.nip.io" (free, browser-trusted HTTPS via Let's Encrypt).
#
# What it does:
#   1. Installs Docker Engine + compose plugin (if missing).
#   2. Generates a .env with strong secrets (if missing).
#   3. Builds and starts the full stack behind Caddy HTTPS on ports 80/443.
#
# Prereqs you must do yourself (cloud account actions):
#   - Create the VM, open ports 80 and 443 in the cloud security list / firewall.
#   - Point this script at it (clone the repo, run this).
# ===========================================================================
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

# --- 1. Docker ---------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo ">> Installing Docker…"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
  echo ">> Docker installed. You may need to log out/in for group membership;"
  echo "   this script will use sudo for docker commands in the meantime."
fi

DC="docker compose"
if ! docker compose version >/dev/null 2>&1; then
  DC="docker-compose"
fi
# Use sudo if the current user can't talk to the docker socket yet.
if ! docker info >/dev/null 2>&1; then
  DC="sudo $DC"
fi

# --- 2. Firewall (open 80/443 on the host, in case ufw/iptables is on) -------
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 80/tcp  || true
  sudo ufw allow 443/tcp || true
fi
# Oracle Ubuntu images ship with iptables rules that block everything but SSH.
if command -v iptables >/dev/null 2>&1; then
  sudo iptables -I INPUT -p tcp --dport 80  -j ACCEPT 2>/dev/null || true
  sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
  # Persist if netfilter-persistent is available.
  command -v netfilter-persistent >/dev/null 2>&1 && sudo netfilter-persistent save || true
fi

# --- 3. SITE_ADDRESS ---------------------------------------------------------
SITE_ADDRESS="${1:-}"
if [ -z "$SITE_ADDRESS" ]; then
  IP="$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me || true)"
  if [ -z "$IP" ]; then
    echo "!! Could not auto-detect public IP. Pass it explicitly:"
    echo "   bash deploy/setup.sh <your-public-ip>.nip.io"
    exit 1
  fi
  SITE_ADDRESS="${IP}.nip.io"
fi
echo ">> Public URL will be: https://${SITE_ADDRESS}"

# --- 4. .env with strong secrets --------------------------------------------
if [ ! -f .env ]; then
  echo ">> Generating .env with random secrets…"
  cp .env.example .env
  SECRET="$(openssl rand -base64 48 | tr -d '\n')"
  # Fernet key = urlsafe base64 of 32 bytes.
  FERNET="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
  sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${SECRET}|" .env
  sed -i "s|^CREDENTIALS_ENCRYPTION_KEY=.*|CREDENTIALS_ENCRYPTION_KEY=${FERNET}|" .env
  sed -i "s|^DJANGO_DEBUG=.*|DJANGO_DEBUG=0|" .env
  echo "   (edit .env to add ANTHROPIC_API_KEY for free-form NL→regex)"
fi

# --- 5. Build + start --------------------------------------------------------
echo ">> Building and starting the stack (first build downloads Spark + jars)…"
export SITE_ADDRESS
$DC -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ""
echo "==================================================================="
echo " Deployed.  Open:  https://${SITE_ADDRESS}"
echo " (First load waits a few seconds while Caddy obtains the TLS cert.)"
echo " Logs:   $DC -f docker-compose.yml -f docker-compose.prod.yml logs -f"
echo " Stop:   $DC -f docker-compose.yml -f docker-compose.prod.yml down"
echo "==================================================================="
