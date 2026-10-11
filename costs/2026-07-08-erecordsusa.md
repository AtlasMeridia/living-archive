# eRecordsUSA Digitization

**Date opened:** 2026-07-08 PDT  
**Vendor:** eRecordsUSA  
**Reference:** eRUSA1278  
**Status:** Approved to proceed by email on 2026-07-08 PDT  
**Project:** Living Archive / Liu family source-material digitization

## Scope

- Liu genealogy book, scanned non-destructively.
- Approximately 200 handwritten letters and postcards.
- Letters to be removed, digitized, and returned/reassembled as received.
- Postcards scanned as 2-page views.
- Sequential file naming as shown in the vendor sample set.

## Estimate

| Item | Basis |
|------|-------|
| Book scans | 600 dpi full color |
| Letters/postcards | 400 dpi full color |
| Unit price | About $1.00 per scan |
| Estimated volume | Over 2,000 images |
| Estimated cost | Around $2,000 |
| Final billing | Based on actual number of images processed |

## Project Notes

The sample PDFs are image-only, with no embedded text layer. The existing
`pypdf` document pipeline will not extract useful text from these scans, so
the downstream ingestion path needs OCR or a vision-PDF analysis route before
these materials can become searchable Living Archive documents.

Treat this as layer-zero source digitization. Preserve vendor outputs exactly
as received, then derive OCR, manifests, and any future view/catalog records
from those files.
