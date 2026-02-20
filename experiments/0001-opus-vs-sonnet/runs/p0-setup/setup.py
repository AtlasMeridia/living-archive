#!/usr/bin/env python3
"""Phase 0: Lock test set inputs and extract text.

Produces:
  - locked-inputs.json: SHA-256 hashes, paths, page counts
  - extracted/{sha[:12]}.json: cached text per document
  - revision.txt: git commit hash
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from src.doc_extract_text import extract_text
from src.doc_scan import get_page_count

SETUP_DIR = Path(__file__).resolve().parent
EXTRACTED_DIR = SETUP_DIR / "extracted"
EXTRACTED_DIR.mkdir(exist_ok=True)

DOC_ROOT = Path("/Volumes/MNEME/05_PROJECTS/Living Archive/Family/Documents/Liu Family Trust Filings & Documents")

TEST_DOCS = [
    "2010-04-14 Quitclaim Deed.pdf",
    "Artifacts/Countries Visited.pdf",
    "2007-05-10 Will of Feng Kuang Liu.pdf",
    "1970-08-29 Investment Record.pdf",
    "Medical/2004-06-16 MEICHU LIU HR Letter.pdf",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    # Record git revision
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    ).stdout.strip()
    (SETUP_DIR / "revision.txt").write_text(rev + "\n")
    print(f"Revision: {rev}")

    locked = []
    for rel_path in TEST_DOCS:
        pdf_path = DOC_ROOT / rel_path
        if not pdf_path.exists():
            print(f"  ERROR: {pdf_path} not found")
            sys.exit(1)

        sha = sha256_file(pdf_path)
        pages = get_page_count(pdf_path)
        size = pdf_path.stat().st_size

        print(f"\n[{len(locked)+1}/{len(TEST_DOCS)}] {rel_path}")
        print(f"  SHA-256: {sha[:12]}...  Pages: {pages}  Size: {size/1024/1024:.1f} MB")

        # Extract text
        result = extract_text(pdf_path)
        print(f"  Extracted: {result.chars_extracted} chars from {result.total_pages} pages")

        # Cache extraction
        cache = {
            "source_file": rel_path,
            "source_sha256": sha,
            "file_size_bytes": size,
            "page_count": pages,
            "total_pages_extracted": result.total_pages,
            "chars_extracted": result.chars_extracted,
            "is_empty": result.chars_extracted == 0,
            "chunks": [
                {
                    "text": text,
                    "page_index": i,
                }
                for i, text in enumerate(result.page_texts)
                if text.strip()
            ],
            "full_text": "\n".join(result.page_texts),
        }
        cache_path = EXTRACTED_DIR / f"{sha[:12]}.json"
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n")
        print(f"  Cached: {cache_path.name}")

        locked.append({
            "index": len(locked) + 1,
            "relative_path": rel_path,
            "sha256": sha,
            "file_size_bytes": size,
            "page_count": pages,
            "chars_extracted": result.chars_extracted,
            "is_empty": result.chars_extracted == 0,
        })

    # Write locked inputs
    locked_path = SETUP_DIR / "locked-inputs.json"
    locked_path.write_text(json.dumps(locked, indent=2) + "\n")
    print(f"\nLocked {len(locked)} documents to {locked_path.name}")

    # Summary
    total_chars = sum(d["chars_extracted"] for d in locked)
    total_pages = sum(d["page_count"] for d in locked)
    empty = sum(1 for d in locked if d["is_empty"])
    print(f"Total: {total_pages} pages, {total_chars} chars, {empty} empty (no text layer)")


if __name__ == "__main__":
    main()
