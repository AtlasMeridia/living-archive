#!/usr/bin/env bash
# One-time VPS setup for the dashboard.
# Run on the VPS: bash setup-vps.sh
#
# Prerequisites:
#   - Deploy key configured in ~/.ssh/deploy_key
#   - Repo cloned at ~/living-archive
#
# After this, run ./deploy/sync.sh from the Mac to push data and start.

set -euo pipefail

STACK_DIR="/opt/stacks/dashboard"
DATA_DIR="/home/atlas/living-archive-data"
REPO_DIR="/home/atlas/living-archive"

echo "=== Living Archive Dashboard — VPS Setup ==="

# Create directories
sudo mkdir -p "$STACK_DIR"
sudo chown -R atlas:atlas "$STACK_DIR"
mkdir -p "$DATA_DIR"

# Copy deployment files from the cloned repo
if [ -d "$REPO_DIR/deploy" ]; then
    cp "$REPO_DIR/deploy/Dockerfile" "$STACK_DIR/"
    cp "$REPO_DIR/deploy/docker-compose.yml" "$STACK_DIR/"
    cp "$REPO_DIR/deploy/requirements.txt" "$STACK_DIR/"
else
    echo "ERROR: Repo not found at $REPO_DIR — clone it first."
    exit 1
fi

# Create .env if it doesn't exist
if [ ! -f "$STACK_DIR/.env" ]; then
    cp "$REPO_DIR/deploy/.env.example" "$STACK_DIR/.env"
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
