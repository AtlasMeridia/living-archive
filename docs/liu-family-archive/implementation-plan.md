# Liu Family Archive — Implementation Plan

> [!NOTE]
> **Historical Document** — This plan was written Dec 2025 before infrastructure decisions were made. The actual implementation uses NAS (Synology DS923+) + Immich rather than Cloudflare R2 + Hugo. See `docs/architecture.md` for current infrastructure.
>
> Valuable reference sections: SQLite schema design, data model concepts, content governance, longevity planning.

> **Note:** This document is part of the Living Archive project's personal case study. The Liu family archive work demonstrates the methodology documented in the parent project. See `/project-brief.md` for the broader Living Archive scope.

**Prepared:** December 25, 2025  
**Revised:** January 11, 2026  
**Status:** Reference document for personal archive work  
**Development Model:** Solo developer + Claude Code AI-assisted development

---

## Executive Summary

This plan outlines the technical infrastructure for the Every Branch Archive, a multi-generational family history project. The architecture prioritizes:

- **50+ year longevity** through technology choices that minimize migration needs
- **Minimal maintenance** for a solo developer
- **Bilingual support** (English / Traditional Chinese)
- **Tiered privacy** with family-only sections

### Recommended Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Photo Storage** | Cloudflare R2 | Zero egress fees, native Cloudflare integration, simple auth |
| **Database** | SQLite | 50-year support commitment, Library of Congress approved |
| **Static Site** | Hugo | Single binary, fastest builds, native i18n, no JS runtime |
| **Hosting** | Cloudflare Pages | Unlimited free bandwidth, public company stability |
| **Authentication** | Cloudflare Access | Free for 50 users, email-based login |

### Estimated Costs

| Period | Cost |
|--------|------|
| 10 years | ~$500-650 (domain + storage) |
| 20 years | ~$1,000-1,300 |

### Minimum Viable Archive (Launch Criteria)

The archive is "launch-ready" when it meets these concrete thresholds:

| Metric | Target | Rationale |
|--------|--------|-----------|
| **People entered** | 30+ | Enough to show family structure across 3 generations |
| **Photos uploaded** | 150+ | Critical mass for browsing to feel worthwhile |
| **Photos tagged** | 75% of uploaded | Untagged photos have limited value |
| **Family testers** | 3 members | Validates auth and usability before wider rollout |
| **Bilingual coverage** | 100% of UI, 50% of content | Core pages fully translated |

**Launch is not blocked by:**
- Complete photo digitization (ongoing)
- Red book integration (Phase 5)
- Perfect data—corrections can happen post-launch

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLOUDFLARE                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Cloudflare     │  │  Cloudflare R2  │  │  Cloudflare     │  │
│  │  Pages          │  │  (Photo/Doc     │  │  Access         │  │
│  │  (Hugo site)    │  │   Storage)      │  │  (Auth layer)   │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
│           │                    │                    │            │
│           └────────────────────┼────────────────────┘            │
│                                │                                 │
│                    ┌───────────▼───────────┐                     │
│                    │    Custom Domain      │                     │
│                    │  everybranch.family   │                     │
│                    └───────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     LOCAL / GIT REPO                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Hugo Source    │  │  SQLite DB      │  │  Photo/Doc      │  │
│  │  (Markdown,     │  │  (Primary data  │  │  Originals      │  │
│  │   templates)    │  │   store)        │  │  (backed up)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Content Creation:** Markdown files + SQLite database maintained locally
2. **Build:** Hugo generates static HTML/CSS/JS
3. **Deploy:** Git push triggers Cloudflare Pages build
4. **Photos:** Uploaded to R2, referenced by URL in site
5. **Access:** Public pages served directly; `/family/*` routes gated by Cloudflare Access

---

## 2. Photo Infrastructure

### Storage: Cloudflare R2

**Why R2 over Backblaze B2:**
- Single provider for everything (simpler architecture)
- Zero egress fees regardless of access patterns
- Native Workers integration for authentication
- No Terms of Service concerns about serving media

**Pricing (2025):**
- Storage: $0.015/GB/month (standard) or $0.01/GB (infrequent access)
- Egress: Free
- Free tier: 10GB storage

**10-Year Cost Projection:**
- Starting at 50GB, growing to 500GB: ~$330-500 total

### Organization Structure

```
R2 Bucket: every-branch-photos/
├── originals/
│   ├── a1/                    # First 2 chars of SHA-256 hash
│   │   └── a1b2c3d4e5f6...jpg
│   └── ...
├── web/                       # Resized for web (generated)
│   ├── a1/
│   │   ├── a1b2c3d4..._1200.jpg
│   │   └── a1b2c3d4..._400.jpg
│   └── ...
└── documents/
    ├── letters/
    ├── certificates/
    └── zupu/
```

**Content-addressable storage** (hash-based paths):
- Automatic deduplication
- Verifiable integrity
- No filename conflicts

### Upload Workflow

1. Hash file locally (SHA-256)
2. Check if hash exists in R2
3. Upload original to `originals/{hash[0:2]}/{hash}.{ext}`
4. Generate web-sized versions
5. Record metadata in SQLite

### Access Control

**Approach:** Cloudflare Worker middleware

```javascript
// R2 access control via Cloudflare Worker
// Validates Cloudflare Access JWT before serving private photos

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const objectKey = url.pathname.slice(1); // Remove leading slash

    // Verify Cloudflare Access JWT
    const jwt = request.headers.get('Cf-Access-Jwt-Assertion');
    if (!jwt) {
      return new Response('Unauthorized', { status: 401 });
    }

    // Validate JWT (Cloudflare Access handles this automatically
    // when Access is configured for this route)
    // For additional validation, verify against:
    // https://<team>.cloudflareaccess.com/cdn-cgi/access/certs

    // Fetch from R2
    const object = await env.PHOTOS_BUCKET.get(objectKey);
    if (!object) {
      return new Response('Not Found', { status: 404 });
    }

    // Return with appropriate headers
    const headers = new Headers();
    headers.set('Content-Type', object.httpMetadata?.contentType || 'image/jpeg');
    headers.set('Cache-Control', 'private, max-age=3600');

    return new Response(object.body, { headers });
  }
}
```

*Note: If using Cloudflare Access for the entire `/family/*` path, the Worker may be unnecessary—Access handles auth before the request reaches R2. The Worker is useful for fine-grained per-photo access control or custom logic.*

### Backup Strategy

| Backup Type | Frequency | Location | Retention |
|-------------|-----------|----------|-----------|
| R2 Primary | Continuous | Cloudflare | Always |
| Local Mirror | Monthly | External SSD | Rolling 3 copies |
| Offsite | Quarterly | Second location | Indefinite |
| M-DISC | Every 5 years | Physical archive | 1000+ years |

---

## 3. Data Model

### Why SQLite

- **Official support commitment through 2050**
- **Library of Congress** recommended format for digital preservation
- **Zero dependencies** — single file, works forever
- **Bit-for-bit identical** across all platforms

### Core Schema

```sql
-- Schema version tracking
CREATE TABLE schema_info (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Core person entity
CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    uuid TEXT UNIQUE NOT NULL,
    birth_date TEXT,                -- ISO 8601
    birth_date_precision TEXT CHECK(birth_date_precision IN
        ('year', 'month', 'day', 'circa', 'unknown')),
    death_date TEXT,
    death_date_precision TEXT,
    sex TEXT CHECK(sex IN ('M', 'F', 'U')),
    birth_place TEXT,
    death_place TEXT,
    is_private BOOLEAN DEFAULT 0,   -- Exclude from public exports
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Bilingual name support with romanization variants
CREATE TABLE person_names (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name_type TEXT NOT NULL CHECK(name_type IN
        ('birth', 'married', 'courtesy', 'generation', 'alias',
         'immigration', 'nickname')),
    full_name TEXT NOT NULL,
    given_name TEXT,
    surname TEXT,
    script TEXT NOT NULL CHECK(script IN
        ('han-traditional', 'han-simplified', 'latin', 'other')),
    language TEXT,                  -- BCP 47: 'zh-Hant', 'en'
    romanization_system TEXT CHECK(romanization_system IN
        ('pinyin', 'wade-giles', 'yale', 'tongyong', 'family',
         'immigration-doc', 'cantonese', 'hokkien', 'hakka', NULL)),
    is_primary BOOLEAN DEFAULT 0,
    source TEXT,                    -- Provenance
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Family relationships
CREATE TABLE relationships (
    id INTEGER PRIMARY KEY,
    relationship_type TEXT NOT NULL CHECK(relationship_type IN
        ('parent-child', 'spouse')),
    person1_id INTEGER NOT NULL REFERENCES persons(id),
    person2_id INTEGER NOT NULL REFERENCES persons(id),
    lineage_type TEXT CHECK(lineage_type IN
        ('biological', 'adopted', 'step', 'foster', 'guardian', 'unknown')),
    start_date TEXT,
    end_date TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Photo metadata
CREATE TABLE photos (
    id INTEGER PRIMARY KEY,
    uuid TEXT UNIQUE NOT NULL,
    file_hash_sha256 TEXT NOT NULL UNIQUE,
    original_filename TEXT,
    r2_path TEXT NOT NULL,          -- Path in R2 bucket
    mime_type TEXT,
    file_size_bytes INTEGER,
    width INTEGER,
    height INTEGER,
    capture_date TEXT,
    capture_date_precision TEXT,
    capture_location TEXT,
    description_en TEXT,
    description_zh TEXT,
    photographer TEXT,
    source TEXT,                    -- 'family_collection', 'ryan_liu', etc.
    is_private BOOLEAN DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Photo-person tagging with face regions
CREATE TABLE photo_persons (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES persons(id),  -- NULL if unidentified
    region_x REAL,                  -- Normalized 0-1 coordinates
    region_y REAL,
    region_width REAL,
    region_height REAL,
    confidence TEXT CHECK(confidence IN
        ('certain', 'probable', 'possible', 'unknown')),
    identified_by TEXT,
    identification_date TEXT,
    identification_source TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Documents (letters, papers, certificates)
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    uuid TEXT UNIQUE NOT NULL,
    file_hash_sha256 TEXT NOT NULL UNIQUE,
    r2_path TEXT NOT NULL,
    document_type TEXT CHECK(document_type IN
        ('letter', 'immigration', 'certificate', 'legal',
         'newspaper', 'zupu_page', 'other')),
    title_en TEXT,
    title_zh TEXT,
    description_en TEXT,
    description_zh TEXT,
    document_date TEXT,
    document_date_precision TEXT,
    language TEXT,
    transcription TEXT,
    is_private BOOLEAN DEFAULT 0,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Zupu (族譜) specific entries
CREATE TABLE zupu_entries (
    id INTEGER PRIMARY KEY,
    person_id INTEGER REFERENCES persons(id),
    generation_number INTEGER,      -- 第幾世
    generation_character TEXT,      -- 輩分字
    branch TEXT,                    -- 房
    original_text TEXT,             -- Raw text from zupu
    source_page TEXT,
    source_edition TEXT,            -- '1983', '2026'
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_person_names_person ON person_names(person_id);
CREATE INDEX idx_person_names_script ON person_names(script);
CREATE INDEX idx_relationships_person1 ON relationships(person1_id);
CREATE INDEX idx_relationships_person2 ON relationships(person2_id);
CREATE INDEX idx_photo_persons_photo ON photo_persons(photo_id);
CREATE INDEX idx_photo_persons_person ON photo_persons(person_id);
CREATE INDEX idx_photos_hash ON photos(file_hash_sha256);
```

### Data Validation and Integrity

**Database-level constraints (enforced by SQLite):**
- Foreign key constraints with `ON DELETE CASCADE` for dependent records
- `CHECK` constraints for enumerated values (sex, name_type, script, etc.)
- `UNIQUE` constraints on UUIDs and file hashes
- `NOT NULL` on required fields

**Application-level validation (enforced by scripts):**

| Rule | Enforcement |
|------|-------------|
| Death date after birth date | Reject on entry |
| Person must have at least one name | Reject on entry |
| No self-relationships | Reject on entry |
| Parent born before child | Warn, allow override |
| Duplicate relationship | Reject on entry |
| Similar names exist | Warn, show matches, allow proceed |

**Duplicate detection:**
- Photos: SHA-256 hash prevents duplicate files automatically
- People: Fuzzy matching on names during entry (warn, don't block)
- Generate periodic "possible duplicates" report for manual review

**Orphan prevention:**
- Run integrity check before exports: `PRAGMA foreign_key_check;`
- Script to find photos with no person tags
- Script to find people with no photos or relationships

### SQLite Concurrency Limitations

**Single-writer model:** SQLite allows only one writer at a time. This is acceptable for this project because:
- Solo developer workflow (no simultaneous editors)
- Photo uploads are not latency-sensitive
- Data entry sessions are infrequent

**If collaboration is needed later:**
- Option A: Serialize edits (one person edits at a time, sync via Git)
- Option B: Export to shared Google Sheet for family input, import periodically
- Option C: Migrate to hosted database (Turso, PlanetScale) — only if truly needed

**Current approach:** Treat the database as single-user. Backup before any bulk operations.

### Version Control Strategy

**In Git (this repository):**
```
/every-branch-archive/
├── schema/
│   ├── schema.sql              # Full DDL
│   └── migrations/
│       ├── 001_initial.sql
│       └── ...
├── exports/                    # Periodic human-readable exports
│   ├── persons.csv
│   ├── relationships.csv
│   └── every_branch.ged        # GEDCOM 7.0 export
├── scripts/
│   ├── export_gedcom.py
│   ├── export_csv.py
│   ├── upload_photos.py
│   └── backup.sh
└── site/                       # Hugo source
```

**NOT in Git (external storage):**
```
/every-branch-data/             # Backed up separately
├── every_branch.sqlite         # The database
├── photos/                     # Original files
└── backups/
```

---

## 4. Website/Frontend

### Static Site Generator: Hugo

**Why Hugo:**
- **Single binary** — no Node.js, no dependencies, runs in 50 years
- **Native i18n** — built-in Traditional Chinese support (`zh-hant`)
- **Fastest builds** — milliseconds even for thousands of pages
- **Go templates** — learning curve, but stable once learned
- **Markdown content** — most portable format

### Bilingual Content Strategy

**File structure:**
```
/site/content/
├── _index.en.md
├── _index.zh-hant.md
├── about/
│   ├── index.en.md
│   └── index.zh-hant.md
├── gallery/
│   ├── _index.en.md
│   ├── _index.zh-hant.md
│   └── photo-001/
│       ├── index.en.md
│       └── index.zh-hant.md
└── family/                     # Protected section
    ├── _index.en.md
    └── _index.zh-hant.md
```

**Hugo config (hugo.toml):**
```toml
defaultContentLanguage = "en"
defaultContentLanguageInSubdir = true

[languages]
  [languages.en]
    languageName = "English"
    weight = 1
  [languages.zh-hant]
    languageName = "繁體中文"
    weight = 2
    hasCJKLanguage = true
```

### Hosting: Cloudflare Pages

**Why Cloudflare Pages:**
- **Unlimited bandwidth** on free tier
- **Public company** — infrastructure is core business, not experiment
- **Global edge network** — fast in both US and Asia
- **Native integration** with R2, Access, Workers
- **Simple deploys** — git push triggers build

**Free tier limits (sufficient for this project):**
- 500 builds/month
- Unlimited bandwidth
- Unlimited static asset requests
- 100,000 function requests/day

### Authentication: Cloudflare Access

**Setup:**
1. Create Access application for `everybranch.family/family/*`
2. Configure email-based login (one-time codes)
3. Add family members by email
4. No code changes required

**Free tier:** 50 users (more than enough for extended family)

**Fallback:** If Access becomes paid, implement HTTP Basic Auth via Pages Functions (documented, simple).

---

## 5. Development Phases

*Note: Phases are ordered by dependency, not calendar time. Estimates are omitted intentionally—scope and life circumstances vary. Track progress against tasks, not dates.*

### Phase 1: Foundation

**Goal:** Basic infrastructure working end-to-end

**1.1 Data Layer (do first—validates the model before cloud costs)**
- [ ] Create SQLite database file with core schema
- [ ] Insert 10 test people with varied name types (birth, courtesy, immigration)
- [ ] Insert 5 test relationships (parent-child, spouse)
- [ ] Write Python script to export persons to Hugo-compatible markdown
- [ ] Validate bilingual content structure renders correctly

**1.2 Local Hugo Site**
- [ ] Initialize Hugo site with bilingual config (`en` + `zh-hant`)
- [ ] Create base templates (list, single, homepage)
- [ ] Implement language switcher component
- [ ] Create person profile template (bilingual)
- [ ] Create photo gallery template
- [ ] Test build with exported test data

**1.3 Cloud Infrastructure**
- [ ] Create Cloudflare account
- [ ] Set up R2 bucket with folder structure (`originals/`, `web/`, `documents/`)
- [ ] Configure R2 public access or Worker proxy
- [ ] Set up Cloudflare Pages project linked to Git repo
- [ ] Configure build command (`hugo --minify`)
- [ ] Verify deploy succeeds with test content

**1.4 Domain & Auth**
- [ ] Register/transfer domain (decision needed: `everybranch.family`?)
- [ ] Configure DNS in Cloudflare
- [ ] Set up Cloudflare Access application for `/family/*`
- [ ] Add 3 test family member emails
- [ ] Verify auth flow works end-to-end

**1.5 Photo Pipeline**
- [ ] Write `upload_photo.py` script (hash → check exists → upload → DB record)
- [ ] Write `generate_web_sizes.py` script (create 1200px and 400px variants)
- [ ] Upload 10 test photos through pipeline
- [ ] Verify photos accessible via site

**Deliverable:** Functional bilingual site with working photo storage and auth. Ready for real content.

### Phase 2: Photo Migration

**Goal:** Existing digitized photos accessible online

**2.1 Batch Upload**
- [ ] Inventory existing digitized photos (count, formats, organization)
- [ ] Run batch upload script on first 50% of collection
- [ ] Verify uploads via spot-checking ~20 random photos
- [ ] Document any upload failures for manual review

**2.2 Basic Metadata Entry**
- [ ] Create spreadsheet template for photo metadata (date, location, description)
- [ ] Enter metadata for priority photos (oldest, most historically significant)
- [ ] Import metadata to SQLite via script

**2.3 Gallery Implementation**
- [ ] Implement photo grid view with lazy loading
- [ ] Implement photo detail page (bilingual captions)
- [ ] Add lightbox/modal for full-size viewing
- [ ] Implement basic filtering (by date range, tagged/untagged)

**2.4 Family Testing**
- [ ] Invite 3 family members as testers
- [ ] Collect feedback on navigation and usability
- [ ] Fix critical issues before wider rollout

**Milestone:** 150+ photos online, browsable by 3+ family members

**Deliverable:** Password-protected photo gallery with existing content

### Phase 3: Data Entry Tools

**Goal:** Efficient workflow for adding people and tagging photos

**3.1 Person Management (CLI recommended for speed)**
- [ ] `add_person.py` — Interactive prompts for names, dates, notes
- [ ] `list_persons.py` — Search/filter people in database
- [ ] `edit_person.py` — Modify existing records
- [ ] Handle bilingual name entry (prompt for both scripts)

**3.2 Photo Tagging Workflow**

*This is the highest-friction task—optimize for speed:*

- [ ] `tag_photos.py` — Display photo, prompt for person IDs
- [ ] Implement "quick tag" mode (show photo, type person ID, next)
- [ ] Support region tagging (face bounding boxes) for group photos
- [ ] Add confidence levels (certain/probable/possible)
- [ ] Track "needs review" queue for uncertain identifications

**Workflow for efficient bulk tagging:**
```
1. Open photo in viewer (automatic)
2. See list of recently-used person IDs
3. Type ID(s) or partial name to search
4. Optionally draw face region
5. Press Enter → next photo
```

**3.3 Relationship Entry**
- [ ] `add_relationship.py` — Link two people with relationship type
- [ ] Validate relationships (no self-references, no impossible dates)
- [ ] Infer reciprocal relationships (if A is parent of B, B is child of A)

**3.4 Export Scripts**
- [ ] `export_csv.py` — Persons, relationships, photos as CSV files
- [ ] `export_gedcom.py` — GEDCOM 7.0 format (see Section 3.5 for mapping)
- [ ] `export_hugo.py` — Generate Hugo markdown from database

**3.5 GEDCOM 7.0 Mapping**

| Database Field | GEDCOM Tag | Notes |
|----------------|------------|-------|
| `person_names.full_name` | `NAME` | Primary name |
| `person_names.name_type='courtesy'` | `NAME.TYPE=aka` | Mapped to alias |
| `person_names.script='han-traditional'` | `NAME.TRAN.LANG=zh-Hant` | Translation tag |
| `persons.birth_date` | `BIRT.DATE` | With precision qualifier |
| `zupu_entries.*` | `_ZUPU` | Custom extension tag |

*GEDCOM doesn't natively support generation names, romanization systems, or zupu-specific data. These export as custom `_` prefixed tags for round-trip fidelity, with loss accepted for standard GEDCOM consumers.*

**Deliverable:** Working data entry system, even if not polished

### Phase 4: Content Population

**Goal:** Systematically add content with measurable milestones

*This phase is ongoing but has concrete checkpoints to maintain momentum:*

**4.1 Photo Digitization Completion**
- [ ] Inventory remaining undigitized photos
- [ ] Prioritize by age/fragility (oldest first)
- [ ] Complete digitization in batches of 50
- [ ] Upload and enter metadata as batches complete

**4.2 Family Member Entry**
- [ ] Enter immediate family from memory (parents, grandparents, siblings)
- [ ] Enter extended family with known information
- [ ] Flag uncertain data with confidence levels
- [ ] Create "unknown" placeholder records for unidentified photo subjects

**4.3 Photo Tagging Sprint**
- [ ] Tag all photos with identifiable subjects
- [ ] Mark "unknown" faces for elder review
- [ ] Generate "identification needed" report for Taiwan trip

**4.4 Elder Interviews (Taiwan Trip)**

*Pre-trip preparation:*
- [ ] Create interview question guide (family structure, stories, photo IDs)
- [ ] Prepare "identification needed" photos (printed or tablet)
- [ ] Test recording equipment
- [ ] Draft consent statement for recordings

*Equipment checklist:*
- Audio recorder (phone backup)
- Tablet/laptop with photo gallery access
- Printed copies of unclear photos
- Notebook for genealogy diagrams drawn by elders

*Interview priorities (by knowledge holder):*
1. Oldest living relatives (health-permitting)
2. Family historians / those interested in genealogy
3. Those who knew previous generation

*During trip:*
- [ ] Conduct interviews (audio recorded with consent)
- [ ] Show unidentified photos for identification
- [ ] Photograph any physical documents/photos not yet digitized
- [ ] Collect contact information for other relatives

*Post-trip:*
- [ ] Backup all recordings (multiple locations)
- [ ] Transcribe key interviews (or summarize)
- [ ] Enter new identifications into database
- [ ] Upload newly digitized photos

**Milestones:**

| Milestone | Criteria | Target |
|-----------|----------|--------|
| **M1: Core Family** | 50+ people, immediate family complete | Pre-Taiwan trip |
| **M2: Interview Complete** | Elder interviews conducted, recordings backed up | Post-Taiwan trip |
| **M3: 75% Tagged** | 75% of photos have at least one person tagged | 3 months post-trip |
| **M4: Full Collection** | 100% of known photos digitized and uploaded | 6 months post-trip |

**Deliverable:** Comprehensive archive with real content, informed by primary sources

### Phase 5: Red Book Integration (April 2026+)

**Goal:** Parse and integrate traditional genealogy

#### Data Layer vs AI Layer Philosophy

The archive maintains two conceptual layers for document processing:

| Layer | Purpose | Contents |
|-------|---------|----------|
| **Data Layer** | Source preservation | Original scans at full quality (PDF, TIFF). Never modified. |
| **AI Layer** | Searchable/parsable | Extracted text, structured metadata, cross-references. |

**Principle:** The data layer stays as close to original as possible—no lossy compression, no "cleaned up" scans. Use SOTA processing technology to populate the AI layer, which can be regenerated as better tools emerge.

**Candidate OCR Tools:**
- [dots.ocr](https://github.com/rednote-hilab/dots.ocr) — High-quality document OCR for PDFs

#### Tasks

- [ ] Receive 2026 red book reprint
- [ ] Scan at archival quality → store in `documents/zupu/` (data layer)
- [ ] Evaluate OCR tools (dots.ocr, etc.) vs manual transcription
- [ ] Extract text → `zupu_entries` table (AI layer)
- [ ] Add women omitted from traditional record
- [ ] Cross-reference with photo identifications

**Deliverable:** Complete digitized genealogy with women included, source PDFs preserved

---

## 6. Longevity Considerations

### Technology Choices for Durability

| Choice | Why It Lasts |
|--------|--------------|
| **SQLite** | Official support through 2050, Library of Congress approved |
| **Hugo binary** | Single file, no dependencies, can archive the binary |
| **Markdown** | Plain text, readable without software |
| **JPEG/PNG** | Universal standards, will be readable for decades |
| **Git** | Standard, distributed, multiple copies everywhere |
| **Cloudflare** | Public company, infrastructure as core business |

### Documentation Requirements

Create and maintain:
- [ ] `SUCCESSION.md` — What happens if owner is incapacitated
- [ ] `ADMIN-GUIDE.md` — How to perform common tasks
- [ ] `TECH-OVERVIEW.md` — Architecture for future maintainers
- [ ] `CREDENTIALS.md` — Secure storage of account access (encrypted)

### Succession Plan (Concrete)

**Designated successors (fill in actual names):**

| Role | Primary | Backup |
|------|---------|--------|
| **Technical maintainer** | [Name] | [Name] |
| **Content authority** | [Name] | [Name] |
| **Account holder** | [Name] | [Name] |

**Credential storage:**
- [ ] Create encrypted file (`credentials.enc`) with all account passwords
- [ ] Store encryption password in password manager shared with successor
- [ ] Alternative: Use a password manager with emergency access feature (1Password, Bitwarden)
- [ ] Physical backup: Sealed envelope in safe deposit box or with attorney

**Accounts to document:**
| Account | Purpose | Recovery Method |
|---------|---------|-----------------|
| Cloudflare | Hosting, R2, Access | Email + 2FA backup codes |
| GitHub | Code repository | Email + 2FA backup codes |
| Domain registrar | Domain ownership | Email + 2FA backup codes |
| Email (for above) | Account recovery | Recovery phone/codes |

**Incapacitation scenarios:**

*Gradual (planned transition):*
1. Train successor on basic operations (add photo, update person)
2. Transfer account ownership where possible
3. Update payment methods to successor's
4. Handoff meeting to walk through systems

*Sudden (unplanned):*
1. Successor locates `SUCCESSION.md` (in repo root)
2. Retrieves credentials from documented location
3. Logs into Cloudflare to verify site is still running
4. If site is down, follows troubleshooting guide
5. Updates payment info within 30 days to prevent service interruption

**Annual succession check:**
- [ ] Verify successor still willing/able
- [ ] Confirm credential access works
- [ ] Update any changed passwords
- [ ] Review and update documentation

### Handoff Considerations

For non-technical family members:
- Document assumes zero technical knowledge
- Include screenshots for common operations
- Provide multiple family members with account access
- Identify and recruit a technically-inclined younger family member as long-term backup

### Backup Redundancy

| What | Where | Frequency |
|------|-------|-----------|
| Git repo | GitHub + local | Every push |
| SQLite database | Local + cloud backup | Weekly |
| Photos (R2) | Cloudflare + local SSD | Monthly sync |
| Full archive | Offsite location | Quarterly |
| M-DISC backup | Physical storage | Every 5 years |

### Testing Strategy

**Schema migration testing:**
- [ ] Create test database with sample data before each migration
- [ ] Run migration on copy, verify data integrity
- [ ] Check foreign key constraints: `PRAGMA foreign_key_check;`
- [ ] Verify row counts match expectations

**Export format validation:**
- [ ] GEDCOM: Test import into at least 2 different applications (e.g., Gramps, Ancestry)
- [ ] CSV: Verify in spreadsheet, check encoding (UTF-8 with BOM for Excel compatibility)
- [ ] Hugo markdown: Build site, spot-check rendered pages

**Backup restoration verification:**
- [ ] Quarterly: Restore SQLite from backup to fresh location, run integrity check
- [ ] Annually: Full disaster recovery drill (restore everything to new machine)

**Photo pipeline testing:**
- [ ] Verify hash calculation matches for known files
- [ ] Test upload with various file types (JPEG, PNG, HEIC)
- [ ] Confirm web-sized variants generated correctly

---

## 7. Solo Developer + AI Workflow

### Repository Structure for Claude Code

```
/every-branch-archive/
├── .claude/
│   └── context.md              # Project context for Claude sessions
├── CLAUDE.md                   # Instructions for AI assistants
├── docs/
│   ├── architecture.md         # System design reference
│   ├── data-dictionary.md      # Schema documentation
│   └── workflows.md            # Common operations
└── ...
```

### Documentation Patterns

**CLAUDE.md** — Include at project root:
```markdown
# Every Branch Archive — AI Assistant Context

## Project Purpose
Multi-generational family archive (Liu family)...

## Key Files
- `schema/schema.sql` — Database schema
- `site/` — Hugo site source
- `scripts/` — Python utilities

## Common Tasks
- Adding a person: [workflow]
- Uploading photos: [workflow]
- Deploying site: `git push` (auto-deploys)

## Constraints
- All content must be bilingual (en + zh-hant)
- Photos stored in R2, referenced by SHA-256 hash
- Privacy: respect is_private flags
```

### Automation Opportunities

| Task | Automation |
|------|------------|
| Photo upload | Script: hash → upload → DB entry |
| Site deploy | Git push triggers Cloudflare build |
| Database backup | Cron job or manual script |
| GEDCOM export | Script run before sharing |
| CSV export | Script for spreadsheet access |

### Session Continuity

- Keep `context.md` updated with recent decisions
- Commit frequently with descriptive messages
- Document "why" not just "what" in code comments

---

## 8. Open Questions for User Decision

### Immediate Decisions Needed

1. **Domain name:** Is `everybranch.family` the intended domain, or something else?

2. **Privacy default:** Should new content be private by default (opt-in to public) or public by default (opt-out)?

3. **Photo organization:** Organize by hash (recommended for deduplication) or by date/event (more human-readable)?

4. **Admin interface:**
   - CLI tools (simpler to build, Claude Code friendly)
   - Local web app (more visual, but more complex)
   - Hybrid (CLI for data, web for viewing)

### Deferred Decisions

5. **Elder interview format:** Audio only? Video? Transcription approach?

6. **Red book OCR:** Wait until book arrives to evaluate OCR vs manual transcription

7. **Family collaboration:** If others want to contribute, what's the workflow? (Can be designed after V1)

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Cloudflare discontinues Pages | Low | Medium | Static files portable anywhere |
| Cloudflare Access becomes paid | Medium | Low | Basic auth fallback ready |
| Solo developer unavailable | Medium | High | Succession documentation |
| Family privacy concerns | Medium | Medium | Consent process, privacy flags |
| Data loss | Low | Critical | Multiple backup locations |
| Technology obsolescence | Low | Medium | Plain text formats, documented |

---

## 10. Content Governance

### Privacy Decision Authority

| Content Type | Who Decides | Default |
|--------------|-------------|---------|
| **Living person info** | That person (or parent if minor) | Private |
| **Deceased person info** | Archive owner | Public |
| **Photos of living people** | All identifiable people | Private |
| **Photos of deceased only** | Archive owner | Public |
| **Documents** | Archive owner | Private |

### Consent Process

**For living family members appearing in photos:**
1. Before publishing, notify the person via email/message
2. Provide link to preview the photo and caption
3. Wait for explicit approval (silence ≠ consent)
4. Record consent in database (`photo_consent` table, to be added)

**For sensitive content:**
- Immigration documents: Default private (legal/financial info)
- Letters: Default private unless clearly historical
- Medical/legal records: Always private

### Dispute Resolution

**If family members disagree about a photo:**
1. Default to the more restrictive preference (keep private)
2. Try to understand the concern
3. If one person wants it public, others want it private → stays private
4. Archive owner has final say only if both parties consent to arbitration

### Corrections Process

**Misidentified person in photo:**
1. Anyone can flag an identification as incorrect
2. Original identifier is notified
3. If agreed, correction is made immediately
4. If disputed, add "identification uncertain" flag, keep both possibilities

**Incorrect dates/facts:**
1. Corrections require source citation when possible
2. Original data preserved in `notes` field with timestamp
3. "Last verified" date tracked

### Data Retention

- **No deletion of historical records** — only privacy flag changes
- **Corrections preserve history** — original values kept in notes
- **Account deletion requests** — remove login access, keep contributed data

---

## Summary

This implementation plan provides a clear path from current state (project brief + 50% digitized photos) to a working family archive. The technology choices prioritize:

1. **Longevity** — SQLite, Hugo, plain files
2. **Simplicity** — Single cloud provider, minimal moving parts
3. **Low cost** — ~$50-65/year ongoing
4. **AI-assisted development** — Documented, automatable workflows

**Key additions in this revision:**

| Addition | Section |
|----------|---------|
| Minimum Viable Archive criteria | Executive Summary |
| Detailed Phase 1 task breakdown | Section 5 |
| Data validation rules | Section 3 |
| SQLite concurrency limitations | Section 3 |
| Testing strategy | Section 6 |
| Content governance policies | Section 10 |
| Concrete succession planning | Section 6 |
| Photo tagging workflow | Section 5, Phase 3 |
| Taiwan trip preparation | Section 5, Phase 4 |
| GEDCOM 7.0 mapping | Section 5, Phase 3 |

The phased approach ensures early wins (photo gallery with first 150 photos) while building toward the complete vision (integrated genealogy with red book by 2026+).

**Immediate next steps:**
1. Resolve open questions in Section 8 (domain, privacy default, admin interface)
2. Begin Phase 1.1: Create SQLite database with schema
3. Enter 10 test people to validate data model

---

*Plan prepared by Claude Code based on research into storage, data modeling, and hosting options. Revised to address execution gaps, testing, governance, and succession planning.*
