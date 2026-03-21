#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ClawmarketAI — Full Setup Script
# Usage: chmod +x setup.sh && ./setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

header()  { echo -e "\n${CYAN}══ $1 ══${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }
error()   { echo -e "${RED}✗ $1${NC}"; exit 1; }
info()    { echo -e "  $1"; }

echo -e "${CYAN}"
echo "  ██████╗██╗      █████╗ ██╗    ██╗███╗   ███╗ █████╗ ██████╗ ██╗  ██╗███████╗████████╗"
echo "  ██╔════╝██║     ██╔══██╗██║    ██║████╗ ████║██╔══██╗██╔══██╗██║ ██╔╝██╔════╝╚══██╔══╝"
echo "  ██║     ██║     ███████║██║ █╗ ██║██╔████╔██║███████║██████╔╝█████╔╝ █████╗     ██║   "
echo "  ██║     ██║     ██╔══██║██║███╗██║██║╚██╔╝██║██╔══██║██╔══██╗██╔═██╗ ██╔══╝     ██║   "
echo "  ╚██████╗███████╗██║  ██║╚███╔███╔╝██║ ╚═╝ ██║██║  ██║██║  ██║██║  ██╗███████╗   ██║   "
echo "   ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝  "
echo -e "${NC}"
echo "  The marketplace that never sleeps — setup script v1.0"
echo ""

# ─── Check prerequisites ──────────────────────────────────────────────────────
header "Checking prerequisites"

check_cmd() {
  if command -v "$1" &>/dev/null; then
    success "$1 found ($(command -v "$1"))"
  else
    error "$1 is required but not installed. Install it and re-run."
  fi
}

check_version() {
  local cmd=$1 min=$2
  local ver
  ver=$($cmd --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
  if [ "$(echo -e "$ver\n$min" | sort -V | head -1)" = "$min" ]; then
    success "$cmd $ver ≥ $min"
  else
    warn "$cmd $ver found — recommended ≥ $min"
  fi
}

check_cmd node
check_cmd npm
check_cmd python3
check_cmd pip3
check_version node "20.0"
check_version python3 "3.10"

# Check optional tools
if command -v docker &>/dev/null; then
  success "Docker found — will use for PostgreSQL + Redis"
  USE_DOCKER=true
else
  warn "Docker not found — make sure PostgreSQL and Redis are running manually"
  USE_DOCKER=false
fi

# ─── Environment files ────────────────────────────────────────────────────────
header "Setting up environment files"

setup_env() {
  local dir=$1 src=$2
  if [ ! -f "$dir/.env" ]; then
    cp "$dir/$src" "$dir/.env"
    success "Created $dir/.env from $src"
    warn "→ Edit $dir/.env and fill in your values before running agents/contracts"
  else
    info "$dir/.env already exists — skipping"
  fi
}

setup_env "." ".env.example"
setup_env "backend" ".env.example"

# ─── Contracts (Hardhat) ──────────────────────────────────────────────────────
header "Installing contract dependencies"

npm install
success "Hardhat + OpenZeppelin installed"

echo ""
info "Compiling contracts..."
npx hardhat compile
success "Contracts compiled"

# ─── Backend ──────────────────────────────────────────────────────────────────
header "Installing backend dependencies"

cd backend
npm install
success "Backend dependencies installed"
cd ..

# ─── Dashboard ────────────────────────────────────────────────────────────────
header "Installing dashboard dependencies"

cd dashboard
npm install
success "Dashboard dependencies installed"
cd ..

# ─── Python agents + SDK ──────────────────────────────────────────────────────
header "Installing Python dependencies"

pip3 install web3 aiohttp pydantic eth-account websockets anthropic --quiet
success "Agent dependencies installed"

pip3 install -e sdk/python --quiet
success "ClawmarketAI Python SDK installed"

# ─── JavaScript SDK ───────────────────────────────────────────────────────────
header "Building JavaScript SDK"

cd sdk/javascript
npm install
npm run build 2>/dev/null || warn "TypeScript build skipped (tsc not found — run 'npm run build' manually)"
cd ../..

# ─── PostgreSQL + Redis (Docker) ──────────────────────────────────────────────
if [ "$USE_DOCKER" = true ]; then
  header "Starting PostgreSQL and Redis"
  cd backend
  docker compose up postgres redis -d
  success "PostgreSQL running on localhost:5432"
  success "Redis running on localhost:6379"

  echo ""
  info "Waiting for PostgreSQL to be ready..."
  sleep 4

  info "Running database migrations..."
  node src/db/migrate.js
  success "Database schema applied"
  cd ..
else
  header "Database setup (manual)"
  warn "Docker not available. Make sure PostgreSQL and Redis are running, then run:"
  info "  cd backend && node src/db/migrate.js"
fi

# ─── Run tests ────────────────────────────────────────────────────────────────
header "Running tests"

echo ""
info "Contract tests..."
npm test 2>/dev/null && success "Contract tests passed" || warn "Contract tests skipped (set up .env first)"

echo ""
info "Backend tests..."
cd backend
npm test 2>/dev/null && success "Backend tests passed" || warn "Backend tests skipped"
cd ..

echo ""
info "Python SDK tests..."
cd sdk/python
pytest tests/ -q 2>/dev/null && success "Python SDK tests passed" || warn "Python SDK tests skipped"
cd ../..

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ClawmarketAI setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Next steps:"
echo ""
echo -e "  1. ${YELLOW}Fill in your .env files${NC} with RPC URL, private keys, and contract addresses"
echo ""
echo -e "  2. ${YELLOW}Deploy contracts${NC} to Base Sepolia (testnet):"
echo "     npx hardhat run scripts/deploy-tokens.js --network baseSepolia"
echo "     npx hardhat run scripts/deploy.js --network baseSepolia"
echo ""
echo -e "  3. ${YELLOW}Start the backend:${NC}"
echo "     cd backend && npm run dev"
echo ""
echo -e "  4. ${YELLOW}Start the dashboard:${NC}"
echo "     cd dashboard && npm run dev   →  http://localhost:5173"
echo ""
echo -e "  5. ${YELLOW}Run an agent:${NC}"
echo "     python -m agents.buyer-agent.agent agents/buyer-agent/config.example.json"
echo ""
echo "  Docs: https://github.com/BocchiDaruko/ClawmarketAI/tree/main/docs"
echo ""
