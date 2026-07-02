# Living Archive Manifest Schema v2

## Overview

One JSON file per asset, keyed by SHA-256. Four partitions with distinct
authority levels. The manifest is the only synthesis artifact that describes
a single asset — all other synthesis files (indexes, reports, publish state)
are derived from manifests.

**Location:** `synthesis/manifests/{sha256}.json`

## Partitions

### 1. `source` — Immutable facts about the canonical file

These fields are set once at discovery and never change. The file is what
it is. An orchestrator SHOULD NOT overwrite these.

```json
"source": {
  "sha256": "a9cfaf21e66d9e9d9e77c37f0d2cb94509fed220d82f242a37a57b8f0bda610c",
  "path": "Liu Family Trust Filings & Documents/1994-04-02 Weston Dr Letter of Construction Status.pdf",
  "media_type": "document",
  "file_size": 1147105,
  "file_mtime": "2026-01-15T08:30:00Z"
}
```

| Field | Type | Notes |
|-------|------|-------|
| sha256 | string | Content hash. Also the filename. MUST match the key. |
| path | string | Relative path from NAS mount point |
| media_type | enum | `photo` or `document` |
| file_size | integer | Bytes |
| file_mtime | ISO 8601 | Last-modified timestamp of the source file |

Authority: **canonical**. Written by discovery, never updated.

---

### 2. `technical` — Deterministic derivations from the source file

Measurable, reproducible properties. Two different tools should produce
the same values. Overwrite-safe because they're facts about the bits.

```json
"technical": {
  "photo": {
    "width": 2400,
    "height": 3600,
    "rotation": 0,
    "derivative_path": "derivatives/a9cfaf2.jpg"
  },
  "document": {
    "page_count": 2,
    "chars_extracted": 3703,
    "text_path": "text/a9cfaf21e66d.txt"
  }
}
```

Photo-specific OR document-specific — not both. An orchestrator checks
`source.media_type` to know which sub-object to expect.

| Field | Type | Context | Notes |
|-------|------|---------|-------|
| width | integer | photo | Pixels |
| height | integer | photo | Pixels |
| rotation | enum 0,90,180,270 | photo | Clockwise correction for display |
| derivative_path | string | photo | Path to TIFF→JPEG conversion, relative to synthesis/ |
| page_count | integer | document | From pypdf |
| chars_extracted | integer | document | From text extraction |
| text_path | string | document | Path to extracted text file, relative to synthesis/ |

Authority: **deterministic**. Re-derivable from the source file. Safe to
overwrite on re-run.

---

### 3. `interpretation` — AI-generated and human-corrected knowledge

This is the contestable partition. Claude's best guess, your corrections,
confidence signals. Each field carries its own provenance tag so the
orchestrator knows whether to overwrite on re-run.

**The rule: if `authority` is `"human"`, the orchestrator MUST NOT overwrite
that field. If `"machine"`, it MAY overwrite with a newer inference run.**

```json
"interpretation": {
  "caption": {
    "en": "Letter to Contractor Regarding Remodeling Construction Status at 26471 Weston Drive",
    "zh": "屋主劉豐和劉乃潔寫給金氏營造公司金先生的備忘錄",
    "authority": "machine",
    "confidence": null
  },
  "date": {
    "estimate": "1994-04-02",
    "precision": "day",
    "confidence": 0.95,
    "reasoning": "Date explicitly stated in the letter header.",
    "authority": "machine"
  },
  "people": {
    "identified": ["Feng Liu", "Grace Liu", "Mr. Kim"],
    "count": 3,
    "notes": "Homeowners Feng and Grace Liu; contractor Mr. Kim",
    "authority": "machine",
    "person_ids": []
  },
  "location": {
    "estimate": "Los Altos Hills, CA",
    "confidence": 0.7,
    "authority": "machine"
  },
  "document_type": {
    "value": "personal/letter",
    "authority": "machine"
  },
  "sensitivity": {
    "has_ssn": false,
    "has_financial": true,
    "has_medical": false,
    "authority": "machine"
  },
  "tags": {
    "values": ["property", "correspondence", "construction", "los-altos-hills"],
    "authority": "machine"
  },
  "summary": {
    "en": "A memorandum from homeowners Feng and Grace Liu...",
    "zh": "這是屋主劉豐和劉乃潔寫給金氏營造公司金先生的備忘錄...",
    "authority": "machine"
  },
  "condition": {
    "notes": "Good quality scan, fully legible.",
    "authority": "machine"
  },
  "language": {
    "value": "English",
    "authority": "machine"
  },
  "quality": {
    "value": "fair",
    "authority": "machine"
  },
  "ocr_text": {
    "value": "",
    "authority": "machine"
  }
}
```

Not all fields apply to both media types. Photo manifests use: caption,
date, people, location, tags, condition, ocr_text. Document manifests use:
caption (as title), date, people, document_type, sensitivity, tags,
summary, language, quality. The orchestrator writes whichever fields the
inference produces; absent fields are simply missing, not null.

**Human correction example:**

```json
"date": {
  "estimate": "1994-04-02",
  "precision": "day",
  "confidence": 1.0,
  "reasoning": "Corrected by Kenny from family records.",
  "authority": "human",
  "overridden_from": "circa 1994",
  "corrected_at": "2026-04-27"
}
```

When `authority` is `"human"`, the additional fields `overridden_from` and
`corrected_at` SHOULD be present to preserve the audit trail.

---

### 4. `provenance` — How we know what we know

The audit trail. Every inference run appends an entry. This is how you
tell whether a low-confidence date came from Opus v1 or Sonnet v3, and
whether Kenny ever touched it.

```json
"provenance": {
  "created_at": "2026-03-03T01:03:06Z",
  "updated_at": "2026-04-27T00:15:00Z",
  "history": [
    {
      "run_id": "20260303T005448Z",
      "timestamp": "2026-03-03T01:03:06Z",
      "agent": "pipeline.doc",
      "model": "opus",
      "prompt_version": "document_analysis_v2",
      "input_tokens": 933,
      "output_tokens": 802,
      "fields_written": ["interpretation.caption", "interpretation.date",
                         "interpretation.people", "interpretation.tags",
                         "interpretation.summary", "interpretation.sensitivity"]
    },
    {
      "timestamp": "2026-04-27T00:15:00Z",
      "agent": "human",
      "fields_written": ["interpretation.date"],
      "notes": "Corrected date from family records"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| created_at | ISO 8601 | First manifest creation |
| updated_at | ISO 8601 | Last modification (any partition) |
| history | array | Append-only log of who wrote what |

Each history entry:

| Field | Type | Notes |
|-------|------|-------|
| run_id | string | Batch run identifier (machine runs) |
| timestamp | ISO 8601 | When this entry was written |
| agent | string | What produced this — `pipeline.photo`, `pipeline.doc`, `human`, `reconcile` |
| model | string | Model used (machine runs only) |
| prompt_version | string | Prompt template version (machine runs only) |
| input_tokens | integer | Token cost |
| output_tokens | integer | Token cost |
| fields_written | array | Dot-path list of which fields this run touched |
| notes | string | Free text (human entries) |

The history array is append-only. An orchestrator MUST NOT delete or
modify existing entries — only append. This is where event-sourcing lives
within the state-sourced model: the manifest holds current state, but
provenance.history preserves the full mutation log.

---

## Full Example: Photo Manifest

```json
{
  "source": {
    "sha256": "2502e6624bf714eb99dfdc86df346d2df3fff55eb089b2e78c8b33c611d3423f",
    "path": "2022 Swei Chi/Karina/S__80265234.jpg",
    "media_type": "photo",
    "file_size": 285410,
    "file_mtime": "2022-05-15T04:30:00Z"
  },
  "technical": {
    "width": 3024,
    "height": 4032,
    "rotation": 0,
    "derivative_path": "derivatives/2502e66.jpg"
  },
  "interpretation": {
    "caption": {
      "en": "An elderly woman in her 90s sits in a wheelchair, visited by a younger woman who leans in warmly beside her.",
      "zh": "一位九十多歲的老奶奶坐在輪椅上，一位年輕女性親切地靠在她身旁。",
      "authority": "machine"
    },
    "date": {
      "estimate": "2022",
      "precision": "year",
      "confidence": 0.85,
      "reasoning": "Folder label 2022; face mask visible (COVID era); modern smartphone photo quality.",
      "authority": "machine"
    },
    "people": {
      "identified": ["Swei Chi", "Karina"],
      "count": 3,
      "notes": "Elderly woman likely Swei Chi; younger woman likely Karina based on folder name. Third person in background.",
      "authority": "machine",
      "person_ids": []
    },
    "location": {
      "estimate": "Taiwan — nursing home or care facility",
      "confidence": 0.75,
      "authority": "machine"
    },
    "tags": {
      "values": ["family", "visit", "elderly", "care-facility", "wheelchair", "indoor", "taiwan", "covid-era"],
      "authority": "machine"
    },
    "condition": {
      "notes": "Modern digital photo in good condition. Slight wide-angle distortion typical of phone cameras.",
      "authority": "machine"
    },
    "ocr_text": {
      "value": "",
      "authority": "machine"
    }
  },
  "provenance": {
    "created_at": "2026-02-26T03:56:41Z",
    "updated_at": "2026-02-26T03:56:41Z",
    "history": [
      {
        "run_id": "20260226T035332Z",
        "timestamp": "2026-02-26T03:56:41Z",
        "agent": "pipeline.photo",
        "model": "opus",
        "prompt_version": "photo_analysis_v1",
        "input_tokens": 5,
        "output_tokens": 1188,
        "fields_written": ["interpretation.caption", "interpretation.date",
                           "interpretation.people", "interpretation.location",
                           "interpretation.tags", "interpretation.condition"]
      }
    ]
  }
}
```

---

## Full Example: Document Manifest

```json
{
  "source": {
    "sha256": "a9cfaf21e66d9e9d9e77c37f0d2cb94509fed220d82f242a37a57b8f0bda610c",
    "path": "Liu Family Trust Filings & Documents/1994-04-02 Weston Dr Letter of Construction Status.pdf",
    "media_type": "document",
    "file_size": 1147105,
    "file_mtime": "2026-01-15T08:30:00Z"
  },
  "technical": {
    "page_count": 2,
    "chars_extracted": 3703,
    "text_path": "text/a9cfaf21e66d.txt"
  },
  "interpretation": {
    "caption": {
      "en": "Letter to Contractor Regarding Remodeling Construction Status at 26471 Weston Drive",
      "zh": "屋主劉豐和劉乃潔寫給金氏營造公司金先生的備忘錄",
      "authority": "machine"
    },
    "date": {
      "estimate": "1994-04-02",
      "precision": "day",
      "confidence": 0.95,
      "reasoning": "Date explicitly stated in the letter header.",
      "authority": "machine"
    },
    "people": {
      "identified": ["Feng Liu", "Grace Liu", "Mr. Kim"],
      "count": 3,
      "notes": "Homeowners and contractor",
      "authority": "machine",
      "person_ids": []
    },
    "document_type": {
      "value": "personal/letter",
      "authority": "machine"
    },
    "sensitivity": {
      "has_ssn": false,
      "has_financial": true,
      "has_medical": false,
      "authority": "machine"
    },
    "tags": {
      "values": ["property", "correspondence", "construction", "los-altos-hills"],
      "authority": "machine"
    },
    "summary": {
      "en": "A memorandum from homeowners Feng and Grace Liu to Mr. Kim regarding remodeling progress...",
      "zh": "這是屋主劉豐和劉乃潔寫給金氏營造公司金先生的備忘錄...",
      "authority": "machine"
    },
    "language": {
      "value": "English",
      "authority": "machine"
    },
    "quality": {
      "value": "fair",
      "authority": "machine"
    }
  },
  "provenance": {
    "created_at": "2026-03-03T01:03:06Z",
    "updated_at": "2026-03-03T01:03:06Z",
    "history": [
      {
        "run_id": "20260303T005448Z",
        "timestamp": "2026-03-03T01:03:06Z",
        "agent": "pipeline.doc",
        "model": "opus",
        "prompt_version": "document_analysis_v2",
        "input_tokens": 933,
        "output_tokens": 802,
        "fields_written": ["interpretation.caption", "interpretation.date",
                           "interpretation.people", "interpretation.document_type",
                           "interpretation.sensitivity", "interpretation.tags",
                           "interpretation.summary", "interpretation.language",
                           "interpretation.quality"]
      }
    ]
  }
}
```

---

## Migration from Current Format

Current manifests have a flat structure: `source_file`, `source_sha256`,
`analysis` (all interpretation mixed together), `inference` (single run,
not history). Migration mapping:

| Current | New |
|---------|-----|
| `source_file` | `source.path` |
| `source_sha256` | `source.sha256` |
| (inferred) | `source.media_type` |
| (inferred) | `source.file_size` |
| (inferred) | `source.file_mtime` |
| `rotation` | `technical.rotation` |
| `extraction.chars_extracted` | `technical.chars_extracted` |
| `extraction.text_file` | `technical.text_path` |
| `page_count` | `technical.page_count` |
| `analysis.*` | `interpretation.*` (each field wrapped with `authority: "machine"`) |
| `inference` | First entry in `provenance.history` |
| (new) | `provenance.created_at`, `provenance.updated_at` |

The `raw_response` field in current inference metadata is dropped — it
doubles manifest size without adding value. The structured fields capture
everything needed; if raw output is wanted, it belongs in a separate file.

---

## Authority Rules Summary

| Partition | Authority | Overwrite rule |
|-----------|-----------|----------------|
| source | canonical | Never. Set once at discovery. |
| technical | deterministic | Always safe. Re-derivable from source. |
| interpretation | mixed | Per-field. `human` → never overwrite. `machine` → may overwrite. |
| provenance | audit | Append-only. Never delete or modify existing entries. |

## Validation Rules

1. `source.sha256` MUST match the filename (minus `.json`)
2. `source.media_type` MUST be `photo` or `document`
3. If `source.media_type` is `photo`, `technical` MUST contain photo-specific fields
4. If `source.media_type` is `document`, `technical` MUST contain document-specific fields
5. Every field in `interpretation` MUST have an `authority` value (`"human"` or `"machine"`)
6. If `authority` is `"human"`, `overridden_from` and `corrected_at` SHOULD be present
7. `provenance.history` MUST be in chronological order
8. `provenance.updated_at` MUST match the timestamp of the most recent history entry
