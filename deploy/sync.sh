#!/usr/bin/env bash
# Sync data and deploy code to VPS.
# Run from the repo root: ./deploy/sync.sh
#
# Code is deployed via git pull (repo cloned at ~/living-archive on VPS).
# Data (catalog.db, synthesis.db, thumbnails, manifests) is rsynced since
# it's gitignored and regeneratable.

set -euo pipefail

VPS="atlas@living-archive-vps"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_REPO="/home/atlas/living-archive"
REMOTE_DATA="/home/atlas/living-archive-data"

echo "=== Living Archive Deploy ==="
echo "  Repo: $REPO_ROOT"
echo "  VPS:  $VPS"
echo ""

# --- Step 1: Deploy code via git pull ---
echo "[1/3] Pulling latest code on VPS..."
ssh "$VPS" "cd $REMOTE_REPO && git pull --ff-only"

# --- Step 2: Checkpoint SQLite WAL files ---
echo "[2/3] Checkpointing SQLite databases..."
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

# --- Restart container ---
echo ""
echo "Restarting dashboard container..."
ssh "$VPS" "cd /opt/stacks/dashboard && docker compose restart"

echo ""
echo "=== Deploy complete ==="
echo "  Immich:    https://living-archive.dev"
echo "  Dashboard: https://dashboard.living-archive.dev"
