# Data Layer Migration Options

Exploring alternatives to the NAS (DS923+) as the primary home for source data (~430GB Family branch). Motivated by recurring NAS mount reliability issues blocking pipeline work.

## Current state

- NAS is only needed for `scan` (inventory) and pipeline runs (reading TIFFs/PDFs)
- AI layer, dashboard, synthesis already live locally on Mac
- Immich runs on NAS via Docker
- Family access via Cloudflare Tunnel (archives.kennyliu.io)

## Options evaluated

### Cloud object storage

| Service | Monthly | Annual | Egress | Notes |
|---------|---------|--------|--------|-------|
| Cloudflare R2 | ~$6.45 | ~$77 | Free | Already in Cloudflare ecosystem; zero egress ideal for pipeline reads |
| Backblaze B2 | ~$2.58 | ~$31 | $0.01/GB | Cheapest raw storage; egress adds up |
| Wasabi | ~$2.97 | ~$36 | Free | 1TB minimum billing ($7/mo floor) |
| Hetzner Storage Box | ~$3.49 (1TB) | ~$42 | Included | Mountable via SFTP/SMB |
| AWS S3 Infrequent | ~$5.38 | ~$65 | $0.09/GB | Overkill; expensive egress |

### Local external SSD

- ~$60-80 one-time for 1TB portable SSD
- USB-C speeds, no network latency
- No monthly cost, no cloud dependency
- NAS stays as cold backup

## Recommendation

**Cloudflare R2 (~$7/month)** is the best cloud option — zero egress, existing Cloudflare relationship, `rclone mount` replaces AFP mount transparently.

**External SSD (~$70 once)** is the most pragmatic if the main pain is just "NAS not mounted during pipeline runs." Fastest reads, simplest setup.

## Migration steps (if cloud)

1. `rclone sync` the 430GB to R2 (free ingress)
2. `rclone mount r2:living-archive /Volumes/Archive` replaces AFP mount
3. Decide on Immich hosting:
   - Run locally on M4 Max via Docker
   - Move to a cheap VPS (Hetzner CX22 ~$4/mo)
   - Keep on NAS (already has processed photos, fed via API)
4. NAS becomes cold backup — stop depending on it being mounted

## Open questions

- Does the 726GB Personal branch change the calculus? (Roughly doubles all costs)
- Is Immich worth keeping on the NAS if data moves off it?
- Could the M4 Max just run everything locally (Immich + data + pipeline)?
