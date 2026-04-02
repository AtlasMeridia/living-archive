# MNEME Mount Recovery

Purpose: recover from duplicate or stale macOS SMB mounts for the `MNEME` share after reboot, then verify Living Archive is ready.

## Why this exists

On 2026-04-01, macOS had three mountpoints for the same SMB share:

- `/Volumes/MNEME`
- `/Volumes/MNEME-1`
- `/Volumes/MNEME-2`

`MNEME-1` and `MNEME-2` were usable duplicate mounts. The canonical `/Volumes/MNEME` was stale: it still appeared in `mount`, but was unreadable and rejected unprivileged `umount` / `diskutil unmount force` with `Invalid argument`.

The Living Archive code was patched to survive this by:

1. resolving `/Volumes/MNEME*` aliases automatically
2. checking real directory I/O in preflight instead of bare `Path.exists()`
3. resolving Claude OAuth tokens from Hermes profile envs (`~/.hermes/profiles/*/.env`)

## Goal after reboot

Get back to one clean, readable SMB mount:

- desired: `/Volumes/MNEME`
- not desired: `/Volumes/MNEME-1`, `/Volumes/MNEME-2`

## Step 1 — inspect mounts

Run:

```bash
mount | grep '/Volumes/MNEME' || true
```

Healthy result:

```bash
//mneme_admin@mneme.local/MNEME on /Volumes/MNEME (smbfs, nodev, nosuid, mounted by atlas)
```

Unhealthy result patterns:

- multiple entries (`MNEME-1`, `MNEME-2`)
- only `MNEME-1` / `MNEME-2` and no canonical `MNEME`
- `MNEME` exists but is unreadable

## Step 2 — mount the canonical share once

Preferred method:

```bash
open 'smb://mneme.local/MNEME'
```

Or Finder:

- Go -> Connect to Server
- `smb://mneme.local/MNEME`

Wait a few seconds, then re-check:

```bash
mount | grep '/Volumes/MNEME' || true
```

## Step 3 — verify readability

Run:

```bash
python3 - <<'PY'
from pathlib import Path
for p in ['/Volumes/MNEME', '/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media']:
    path = Path(p)
    try:
        ok = path.exists() and (any(True for _ in path.iterdir()) if path.is_dir() else False)
        print(f'{p}: exists={path.exists()} usable={ok}')
    except Exception as e:
        print(f'{p}: exists={path.exists()} usable=False err={type(e).__name__}')
PY
```

Healthy result:

- `/Volumes/MNEME: exists=True usable=True`
- `/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Media: exists=True usable=True`

## Step 4 — verify Living Archive preflight

Use the same Python that cron uses:

```bash
cd ~/Projects/living-archive
/Users/atlas/.pyenv/versions/3.11.10/bin/python -m src.preflight
```

Healthy result should include all of these:

- `NAS mounted:`
- `Slice directory:`
- `Immich reachable:`
- `OAuth token: configured`
- `All checks passed.`

## Step 5 — optional dry run

This confirms batch discovery without doing work:

```bash
cd ~/Projects/living-archive
/Users/atlas/.pyenv/versions/3.11.10/bin/python -m src.run_batch --hours 0.01 --dry-run
```

Healthy result should show:

- a valid run ID
- `Preflight...`
- `Discovering unprocessed albums...`
- a work list with remaining albums/photos
- `Dry run — exiting without processing.`

## If duplicates come back

Check again:

```bash
mount | grep '/Volumes/MNEME' || true
```

If you see `MNEME-1` / `MNEME-2` again, macOS mounted the same share more than once. Usually that means:

- the canonical `MNEME` path was stale or occupied
- Finder / scripts / reconnect logic mounted the share again
- hostname and IP mounts mixed (`mneme.local` vs `10.10.0.2`)

Use only this canonical endpoint going forward:

```bash
smb://mneme.local/MNEME
```

Avoid mounting the same share by IP when possible.

## Known current software-side mitigations

These are already in the repo as of 2026-04-01:

- `src/config.py`
  - resolves `/Volumes/MNEME*` aliases
- `src/preflight.py`
  - verifies real NAS I/O, not just `Path.exists()`
- `src/auth.py`
- `src/maxplan.py`
  - resolve `CLAUDE_CODE_OAUTH_TOKEN` from Hermes profile envs as well as default env

## Fast success checklist

After reboot, these four checks are enough:

```bash
mount | grep '/Volumes/MNEME' || true
cd ~/Projects/living-archive && /Users/atlas/.pyenv/versions/3.11.10/bin/python -m src.preflight
cd ~/Projects/living-archive && /Users/atlas/.pyenv/versions/3.11.10/bin/python -m src.run_batch --hours 0.01 --dry-run
python3 - <<'PY'
from src.auth import resolve_token
print(resolve_token()[1])
PY
```

Expected outcomes:

- one canonical readable mount
- preflight passes
- dry-run discovers albums
- token source resolves from a Hermes env file (likely `~/.hermes/profiles/nadine/.env`)
