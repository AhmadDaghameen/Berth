#!/usr/bin/env bash
# Run this script INSIDE a WSL2 Ubuntu shell to set up Docker Engine + berth.
# Usage:  bash /mnt/c/Projects/Berth/scripts/setup-wsl2-docker.sh

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
info() { echo -e "${YELLOW}-->${NC}  $*"; }

# ── 1. Docker Engine ────────────────────────────────────────────────────────
# Check for real Docker Engine — not the Docker Desktop WSL shim
DOCKER_REAL=false
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    DOCKER_REAL=true
fi

if $DOCKER_REAL; then
    ok "Docker Engine already installed and running ($(docker --version))"
elif dpkg -l docker-ce &>/dev/null 2>&1; then
    ok "Docker Engine package present ($(docker --version 2>/dev/null || echo 'daemon not yet started'))"
else
    info "Installing Docker Engine (real daemon, not Desktop shim) …"
    sudo apt-get update -qq
    sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker "$USER"
    ok "Docker Engine installed. Re-open this shell after setup for group membership."
fi

# ── 2. Start Docker daemon ──────────────────────────────────────────────────
if docker ps &>/dev/null 2>&1; then
    ok "Docker daemon is running"
else
    info "Starting Docker daemon …"
    # Try systemd first (available when /etc/wsl.conf has [boot] systemd=true)
    if systemctl is-system-running &>/dev/null 2>&1; then
        sudo systemctl start docker
    else
        # Fallback: SysV init or direct dockerd
        if [ -f /etc/init.d/docker ]; then
            sudo service docker start
        else
            info "Starting dockerd directly (no init script found) …"
            sudo dockerd &>/tmp/dockerd.log &
            sleep 3
        fi
    fi
    sleep 2
    docker ps &>/dev/null && ok "Docker daemon started" || {
        echo "ERROR: could not start Docker daemon."
        echo "  Try enabling systemd: echo '[boot]\\nsystemd=true' | sudo tee /etc/wsl.conf"
        echo "  Then run: wsl --shutdown  (in PowerShell), reopen Ubuntu, re-run this script."
        exit 1
    }
fi

# ── 3. mkcert ───────────────────────────────────────────────────────────────
if command -v mkcert &>/dev/null; then
    ok "mkcert already installed ($(mkcert -version 2>&1 | head -1))"
else
    info "Installing mkcert …"
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  MKCERT_ARCH="amd64" ;;
        aarch64) MKCERT_ARCH="arm64" ;;
        *)       MKCERT_ARCH="amd64" ;;
    esac
    LATEST=$(curl -s https://api.github.com/repos/FiloSottile/mkcert/releases/latest \
             | grep '"tag_name"' | cut -d'"' -f4)
    curl -fsSL "https://github.com/FiloSottile/mkcert/releases/download/${LATEST}/mkcert-${LATEST}-linux-${MKCERT_ARCH}" \
         -o /tmp/mkcert
    chmod +x /tmp/mkcert
    sudo mv /tmp/mkcert /usr/local/bin/mkcert
    ok "mkcert installed ($(mkcert -version 2>&1 | head -1))"
fi

# ── 4. Python + berth ───────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    info "Installing Python 3 …"
    sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
fi

if ! command -v pip3 &>/dev/null; then
    sudo apt-get install -y -qq python3-pip
fi

BERTH_DIR="/mnt/c/Projects/Berth"
if [ -d "$BERTH_DIR" ]; then
    info "Installing berth from $BERTH_DIR …"
    pip3 install -e "$BERTH_DIR" --quiet
    ok "berth installed ($(berth --help 2>&1 | head -1))"
else
    echo "WARNING: $BERTH_DIR not found. Install berth manually: pip3 install -e /path/to/Berth"
fi

# ── 5. Summary ──────────────────────────────────────────────────────────────
echo ""
echo "============================================"
ok "WSL2 Docker environment ready!"
echo ""
echo "  Next steps (run from WSL2 shell):"
echo "    sudo berth setup"
echo "    berth register /mnt/c/Projects/Berth/sample/demo"
echo "    berth up demo"
echo ""
echo "  Note: 'berth setup' writes to the hosts file — needs sudo."
echo "  For the Windows browser to resolve *.test, berth will also"
echo "  write to /mnt/c/Windows/System32/drivers/etc/hosts (auto)."
echo "============================================"
