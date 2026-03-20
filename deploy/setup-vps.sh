#!/usr/bin/env bash
# One-time VPS setup for the dashboard.
# Run on the VPS: bash setup-vps.sh
#
# After this, run sync.sh from the Mac to populate app/ and data,
# then: cd /opt/stacks/dashboard && docker compose up -d --build

set -euo pipefail

STACK_DIR="/opt/stacks/dashboard"
DATA_DIR="/home/atlas/living-archive-data"

echo "=== Living Archive Dashboard — VPS Setup ==="

# Create directories
sudo mkdir -p "$STACK_DIR/app/src"
sudo chown -R atlas:atlas "$STACK_DIR"
mkdir -p "$DATA_DIR"

# Copy deployment files
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/Dockerfile" "$STACK_DIR/"
cp "$SCRIPT_DIR/docker-compose.yml" "$STACK_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$STACK_DIR/"

# Create .env if it doesn't exist
if [ ! -f "$STACK_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$STACK_DIR/.env"
    echo ""
    echo "  Created $STACK_DIR/.env from template."
    echo "  Edit it to set IMMICH_API_KEY before starting."
else
    echo "  $STACK_DIR/.env already exists, skipping."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $STACK_DIR/.env — set IMMICH_API_KEY"
echo "  2. From Mac: ./deploy/sync.sh"
echo "  3. On VPS:  cd $STACK_DIR && docker compose up -d --build"
echo "  4. Verify:  curl http://localhost:8378/api/health"
echo "  5. Add Cloudflare Tunnel hostname:"
echo "     dashboard.living-archive.kennyliu.io → http://localhost:8378"
