# Plan: Server-Side Bilingual API (Option B)

## Problem

The dashboard translation system is client-side only. A `ZH` dictionary translates static UI labels (tab names, headings, button text), but dynamic content from API responses renders in English regardless of language setting. This affects:

- **Documents tab**: Document types (`legal/trust`, `financial/statement`, etc.) — 23 unique types
- **Documents tab**: Quality labels (`fair`, `good`, `poor`), language names
- **Health tab**: Check names (`NAS Mount`, `Immich`, `Claude CLI`), config keys, status details
- **Toolbox tab**: Tool names, descriptions, categories, argument strings — all hardcoded in JS as English

## Architecture

Current flow:
```
Python API → JSON (English only) → JS renders → t() translates LABELS only
```

Target flow:
```
Python API → JSON (bilingual fields) → JS picks _lang field → renders
```

## Design Principles

1. **English is the canonical data language.** Chinese is a parallel field, not a replacement.
2. **Every user-visible string from the API gets a `_zh` sibling.** `document_type` + `document_type_zh`.
3. **The JS rendering layer picks based on `_lang`.** A helper like `l(obj, field)` returns `obj[field + '_zh']` or `obj[field]` based on the current language.
4. **Translation happens once at the data layer**, not per-render. The API builds the bilingual response; the client just selects.
5. **Unknown translations fall back to English.** No blank fields.

## Scope

### Layer 1: Translation Dictionary (Python, new file)

New file: `src/translations.py`

A Python dictionary mapping English terms to Traditional Chinese. This is the **single source of truth** — both the API and any future interface reference it.

```python
ZH = {
    # Document types (23 unique)
    "legal/trust": "法律/信託",
    "financial/statement": "財務/報表",
    "legal/contract": "法律/合約",
    "employment/records": "就業/紀錄",
    "personal/certificate": "個人/證書",
    "employment/correspondence": "就業/通信",
    "personal/letter": "個人/書信",
    "legal/deed": "法律/契約",
    "financial/tax-return": "財務/報稅",
    "medical/records": "醫療/紀錄",
    "personal/memorial": "個人/紀念",
    "medical/correspondence": "醫療/通信",
    "government/immigration": "政府/移民",
    # ... all 23 types
    
    # Quality labels
    "fair": "尚可",
    "good": "良好",
    "poor": "不佳",
    
    # Health check names
    "NAS Mount": "NAS 掛載",
    "Immich": "Immich 相簿",
    "Claude CLI": "Claude CLI",
    "Catalog": "目錄資料庫",
    "Data Freshness": "資料新鮮度",
    
    # Tool categories
    "pipeline": "管線",
    "analysis": "分析",
    "infrastructure": "基礎設施",
    "review": "審閱",
    
    # ... tool names, descriptions
}

def zh(key: str) -> str:
    """Translate a string to Traditional Chinese. Returns English if no translation."""
    return ZH.get(key, key)
```

Estimated: ~80-100 entries covering all dynamic content types.

### Layer 2: API Response Enrichment (Python, modify existing)

Each API function that returns user-visible strings gets bilingual fields.

**Changes to `src/dashboard_api.py`:**

```python
from .translations import zh

def api_doc_corpus() -> dict:
    # ... existing code ...
    # Current: types = {"legal/trust": 29, ...}
    # New: types = [{"type": "legal/trust", "type_zh": "法律/信託", "count": 29}, ...]
    types_bilingual = [
        {"type": name, "type_zh": zh(name), "count": count}
        for name, count in type_counts.items()
    ]
    # Same pattern for quality, languages
```

**Affected API functions (8 of 15):**

| Function | Fields to make bilingual |
|----------|------------------------|
| `api_doc_corpus()` | `types[].type`, `quality` keys, `languages` keys |
| `api_doc_search()` | `document_type`, `quality` |
| `api_health()` | `checks[].name`, `checks[].detail`, `config` keys |
| `api_photo_quality()` | `tags[]` (optional — some tags are descriptive) |
| `api_synthesis_overview()` | `top_people[].name` already bilingual (en + zh) ✓ |
| `api_synthesis_person()` | Labels and descriptions mostly come from photo analysis — already bilingual ✓ |
| `api_synthesis_chronology()` | `era_decade` labels |
| `api_people()` | Already bilingual (name_en + name_zh) ✓ |

**Already bilingual (no change needed):** `api_people`, `api_synthesis_person`, `api_synthesis_overview` — these return both `name_en` and `name_zh` from the data layer.

**Not user-visible (skip):** `api_overview` (stat card labels are static HTML, already in client ZH), `api_photo_runs` (dates, numbers), `api_batch_progress` (progress numbers).

### Layer 3: JS Rendering (dashboard.html, modify existing)

**New helper function:**
```javascript
function l(obj, field) {
    // Language-aware field accessor
    if (_lang === 'zh' && obj[field + '_zh']) return obj[field + '_zh'];
    return obj[field];
}
```

**Rendering changes:** Every place the JS renders an API field, wrap in `l()`:

```javascript
// Before:
`<td>${doc.document_type}</td>`

// After:
`<td>${l(doc, 'document_type')}</td>`
```

**Toolbox:** The TOOLS array is hardcoded JS. Two options:
- (a) Move TOOLS to an API endpoint (`api_toolbox()`) and make it bilingual server-side.
- (b) Add `name_zh`, `desc_zh`, `cat_zh` fields directly to the JS array.

Option (b) is simpler since the toolbox doesn't change dynamically. The JS array just gets parallel fields.

### Layer 4: Ask Tab Bilingual Responses

The Ask pipeline already has bilingual data in retrieval (descriptions come in en + zh from photo analysis and document summaries). The composer prompt can be modified to output bilingual answers when `_lang=zh`. This is a Phase 2 enhancement — works without it since the Ask tab returns LLM-composed text.

## File Changes

| File | Change | Size |
|------|--------|------|
| `src/translations.py` | NEW — bilingual dictionary | ~120 lines |
| `src/dashboard_api.py` | Enrich 5 API functions with `_zh` fields | ~60 lines changed |
| `dashboard.html` | Add `l()` helper, update ~15 render functions | ~40 lines changed |
| `dashboard.html` | Add `_zh` fields to TOOLS array | ~80 lines |

**Total: ~300 lines of changes, 1 new file.**

## Migration Path

1. **Create `src/translations.py`** with all terms. This is a one-time effort — pair with a native speaker or LLM for accuracy.
2. **Enrich API responses** — additive only, no breaking changes. Existing clients ignore `_zh` fields.
3. **Update JS rendering** — replace direct field access with `l()` calls.
4. **Test** — toggle language, verify every tab shows Chinese.
5. **Ongoing** — when new document types or tools appear, add them to `translations.py`.

## What This Does NOT Cover

- **Photo analysis descriptions**: Already bilingual (`description_en` + `description_zh`). No change needed.
- **Timeline events**: Already bilingual (`label_en` + `label_zh`). No change needed.
- **Ask tab answers**: Would require the LLM to compose in Chinese. Deferred to a later enhancement.
- **URL slugs, SHA hashes, file paths**: Not translated. These are identifiers, not user-visible text.

## Dependency

This plan has no external dependencies. `translations.py` is a pure Python dict with no imports. The API changes are additive. The JS changes are mechanical.

The only quality dependency is **translation accuracy** — the ZH dictionary should be reviewed by a native Traditional Chinese speaker (or at minimum, cross-checked against the existing ZH entries in dashboard.html which were already reviewed).
