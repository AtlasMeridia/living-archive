#!/usr/bin/env bash
# Sync dashboard code and data to VPS.
# Run from the repo root: ./deploy/sync.sh
#
# Prerequisites:
#   - SSH access to living-archive-vps (via Tailscale or direct)
#   - /opt/stacks/dashboard/ exists on VPS
#   - /home/atlas/living-archive-data/ exists on VPS

set -euo pipefail

VPS="atlas@living-archive-vps"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_APP="/opt/stacks/dashboard/app"
REMOTE_DATA="/home/atlas/living-archive-data"

echo "=== Living Archive Dashboard Sync ==="
echo "  Repo: $REPO_ROOT"
echo "  VPS:  $VPS"
echo ""

# --- Step 1: Checkpoint SQLite WAL files ---
echo "[1/3] Checkpointing SQLite databases..."
python3 -c "
import sqlite3, pathlib
for db in ['catalog.db', 'synthesis.db']:
    p = pathlib.Path('$REPO_ROOT/data') / db
    if p.exists():
        conn = sqlite3.connect(str(p))
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.close()
        print(f'  Checkpointed {db}')
    else:
        print(f'  Skipped {db} (not found)')
"

# --- Step 2: Sync application code + static assets ---
echo "[2/3] Syncing application code..."
rsync -avz --delete \
    --include='src/' \
    --include='src/__init__.py' \
    --include='src/config.py' \
    --include='src/dashboard.py' \
    --include='src/dashboard_api.py' \
    --include='src/haptic_api.py' \
    --include='src/tokens.py' \
    --include='src/models.py' \
    --include='src/people.py' \
    --include='src/catalog.py' \
    --include='src/catalog_cli.py' \
    --include='src/catalog_refresh.py' \
    --include='src/synthesis_queries.py' \
    --include='src/immich.py' \
    --include='src/doc_index.py' \
    --include='src/doc_manifest.py' \
    --include='src/review_models.py' \
    --include='src/review.py' \
    --include='src/manifest.py' \
    --exclude='src/*' \
    --include='dashboard.html' \
    --include='haptic.html' \
    --include='tokens.css' \
    --include='prompts/' \
    --include='prompts/*' \
    --exclude='*' \
    "$REPO_ROOT/" "$VPS:$REMOTE_APP/"

# --- Step 3: Sync data files ---
echo "[3/3] Syncing data files..."
rsync -avz --delete \
    --include='catalog.db' \
    --include='synthesis.db' \
    --include='chronology.json' \
    --include='chronology.md' \
    --include='people/***' \
    --include='photos/' \
    --include='photos/runs/' \
    --include='photos/runs/***' \
    --include='documents/' \
    --include='documents/runs/' \
    --include='documents/runs/***' \
    --exclude='*.db-shm' \
    --exclude='*.db-wal' \
    --exclude='*' \
    "$REPO_ROOT/data/" "$VPS:$REMOTE_DATA/"

echo ""
echo "=== Sync complete ==="
echo "Restart the container if code changed:"
echo "  ssh $VPS 'cd /opt/stacks/dashboard && docker compose restart'"
