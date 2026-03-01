# Reference Projects

Projects, standards, and tools relevant to Living Archive development. Organized by what you'd learn from each, not by category.

Last updated: 2026-02-24

---

## Hardening the Data Layer

### BagIt (Library of Congress)

Standard for packaging digital content for transfer and storage. A "bag" is a directory with a payload, a manifest (checksums for every file), and tag files (metadata about the bag itself).

- **Spec:** https://datatracker.ietf.org/doc/html/rfc8493
- **Python library:** https://github.com/LibraryOfCongress/bagit-python

**What to study:** Your SHA-256 keying and read-only source layer already follow the same instinct. BagIt formalizes it — the manifest + tagmanifest pattern gives you a way to verify payload integrity that's recognized by every digital preservation institution. Worth considering for the NAS data layer: wrap each media source in a bag, then you can verify nothing has drifted.

**Relevance to Living Archive:** High for data layer integrity. Low urgency — your verify step already covers the core need, but BagIt would make it portable and standards-compliant.

### NDSA Levels of Digital Preservation

A maturity model for digital preservation programs. Four levels across five functional areas: storage, fixity, information security, metadata, and file formats.

- **V2 (2019):** https://ndsa.org/publications/levels-of-digital-preservation/
- **Original paper (2013):** https://www.digitalpreservation.gov/documents/NDSA_Levels_Archiving_2013.pdf

**What to study:** Use it as a self-assessment. Where does your current NAS setup fall? Level 1 is "know what you have" (catalog.db). Level 2 is "protect it" (fixity checks, geographic copies). Level 3 is monitoring for integrity over time. Gives you a roadmap for hardening without over-engineering.

**Relevance to Living Archive:** Directly useful for evaluating where you are and planning next steps. The five functional areas map well to your three-layer architecture.

### Archivematica

Open-source digital preservation system implementing the OAIS (Open Archival Information System) reference model. Handles ingest, storage, preservation planning, and access through a web-based dashboard.

- **Site:** https://www.archivematica.org
- **OAIS model overview:** https://www.archivematica.org/en/docs/archivematica-1.18/getting-started/overview/intro/

**What to study:** Not the software itself (it's institutional-scale), but the OAIS functional model it implements: Ingest, Archival Storage, Data Management, Preservation Planning, Administration, Access. These six functions map surprisingly well to what Living Archive already does informally. The vocabulary alone is useful — SIP (Submission Information Package), AIP (Archival Information Package), DIP (Dissemination Information Package) — for thinking about how data moves between your layers.

**Relevance to Living Archive:** Conceptual. You're not going to run Archivematica, but understanding OAIS gives you a vocabulary for what you're building and surfaces gaps (like preservation planning — what happens when TIFF isn't the right format anymore?).

---

## Hardening the AI Layer

### IIIF (International Image Interoperability Framework)

Standard for serving and presenting images on the web. Separates image serving (Image API) from image presentation (Presentation API). Used by museums, libraries, and archives worldwide.

- **Site:** https://iiif.io
- **Image API:** https://iiif.io/api/image/3.0/
- **Presentation API:** https://iiif.io/api/presentation/3.0/

**What to study:** The separation between serving and presenting is the same principle as your three-layer architecture. If you ever want images viewable outside Immich — in the blog, in a custom viewer, by researchers — IIIF is the interoperability standard. The Presentation API's "manifest" concept (a JSON-LD document describing a sequence of images with metadata) rhymes with your per-photo JSON manifests.

**Relevance to Living Archive:** Future-facing. Worth knowing exists, not worth implementing now. Becomes relevant if the presentation layer grows beyond Immich + blog.

### Dublin Core / Schema.org Metadata

Dublin Core is the minimal metadata standard for digital resources (15 core elements: title, creator, date, description, etc.). Schema.org is the structured data vocabulary used by search engines.

- **Dublin Core:** https://www.dublincore.org/specifications/dublin-core/
- **Schema.org ArchiveComponent:** https://schema.org/ArchiveComponent

**What to study:** Your manifest format already captures most of what Dublin Core covers, but you've invented your own field names. If you ever want manifests to be interoperable with other archival systems — or want blog posts to carry structured data that search engines understand — these give you the vocabulary. The Schema.org `ArchiveComponent` type was designed exactly for items within an archival collection.

**Relevance to Living Archive:** Medium. Useful if methodology adoption is a real goal — other people can't easily use your manifests if the schema is bespoke.

---

## Presentation & Making Archives Feel Alive

### Omeka S

Open-source digital archive platform for libraries, museums, and small collections. Models items, item sets, and media as linked entities. Supports public-facing "sites" built from collection items.

- **Site:** https://omeka.org/s/
- **Demo:** https://omeka.org/s/demo/

**What to study:** The "exhibit" concept — curated narratives built from collection items. An exhibit isn't just "here are 50 photos," it's a guided walk through selected items with editorial context. This maps to your blog strategy: each post could be an exhibit that pulls from the archive. Also study how Omeka handles the admin curation vs. public browse split.

**Relevance to Living Archive:** Design inspiration, not adoption. Look at how Omeka S themes present collections and how the item-set → site → page hierarchy works.

### Mukurtu CMS

Community-driven cultural heritage archive platform, originally built for indigenous communities. Key innovation: **cultural protocols** that control who can see what under what conditions.

- **Site:** https://mukurtu.org
- **Protocol docs:** https://mukurtu.org/support/mukurtu-cms-user-guide/

**What to study:** The cultural protocol model. In Mukurtu, every item has access rules: public, community-only, family-only, restricted. This maps directly to your public/private tension — family photos with living people, historical photos, sensitive trust documents, and public methodology posts all need different visibility. Mukurtu solved this problem for indigenous communities; the patterns transfer to family archives.

**Relevance to Living Archive:** High for the access control design you'll eventually need. Especially relevant when family members start browsing and you need to decide what's visible to whom.

### Knight Lab Tools (Northwestern University)

Suite of lightweight, embeddable storytelling tools for the web. All open-source, all designed for non-developers.

- **TimelineJS:** https://timeline.knightlab.com — interactive timelines from a Google Sheet or JSON
- **StoryMapJS:** https://storymap.knightlab.com — location-based narratives
- **JuxtaposeJS:** https://juxtapose.knightlab.com — before/after image comparison
- **GitHub:** https://github.com/NUKnightLab

**What to study:** TimelineJS for a chronological view of the Liu family archive — photos, documents, and events on a single timeline. StoryMapJS for connecting photos to places (the 1993 Europe trip, Taiwan locations, immigration path). JuxtaposeJS for before/after comparisons of scanned vs. AI-enhanced images. All work with JSON data sources, which you already produce.

**Relevance to Living Archive:** Directly usable in the blog. Could embed a TimelineJS instance that pulls from catalog.db exports. Low effort, high presentation value.

### The Pudding

Data journalism site known for visual essays that make complex data accessible. Not a tool — a design reference for how to present technical work to a general audience.

- **Site:** https://pudding.cool
- **Notable pieces:** "Film Dialogue" (visualization of gender in film), "Free Willy" (whale captivity data), "How Music Taste Evolved"

**What to study:** Structure. Every Pudding piece follows a pattern: hook with something visual, reveal complexity gradually, let the reader interact. They prove you can make data-heavy, technical subjects *feel* approachable without dumbing them down. Your blog posts about methodology could follow this pattern — open with a family photo, zoom into what the AI sees, show the metadata flowing through the pipeline.

**Relevance to Living Archive:** Tone and structure reference for the blog series. Not tech to adopt, but a standard to aspire to for the presentation layer.

---

## Individual-Scale Archival Projects

### Perkeep (formerly Camlistore)

Brad Fitzpatrick's (LiveJournal, memcached, Go standard library) personal storage system. Content-addressed, schema-based, with a web UI. The most technically ambitious "one person organizing their digital life" project.

- **Site:** https://perkeep.org
- **GitHub:** https://github.com/perkeep/perkeep
- **Architecture overview:** https://github.com/perkeep/perkeep/blob/master/doc/overview.txt
- **Permanode concept:** https://github.com/perkeep/perkeep/blob/master/doc/schema/permanode.md

**What to study:** The architecture docs, even though the project is slow-moving. Key concepts: blobs (immutable content-addressed chunks), permanodes (mutable references to immutable data, similar to your manifest-per-asset pattern), claims (signed assertions about permanodes). The permanode model — mutable metadata layered on immutable content — is exactly what your AI layer does. Also has a Synology deployment doc.

**Relevance to Living Archive:** Architectural validation. You arrived at similar patterns independently. Reading Perkeep's design rationale may surface edge cases you haven't hit yet.

### PhotoStructure

One-person project building a self-hosted photo manager focused on organizing large, messy collections. Handles dedup, format diversity, and metadata extraction.

- **Site:** https://photostructure.com
- **Architecture:** https://photostructure.com/about/how-photostructure-works/

**What to study:** How a solo developer approaches the scale problem. PhotoStructure deals with the same "thousands of photos in dozens of formats across multiple sources" reality. Their dedup approach (perceptual hashing + metadata matching) is relevant to your upcoming personal data integration where Day One attachments overlap with iCloud Photos.

**Relevance to Living Archive:** Tactical. Most useful when you hit the personal branch's dedup challenge.

### Tropy

Open-source desktop app for organizing research photos taken in archives. Built by the team behind Zotero and Omeka. Designed for historians working with archival materials.

- **Site:** https://tropy.org
- **Docs:** https://docs.tropy.org
- **GitHub:** https://github.com/tropy/tropy

**What to study:** Tropy's metadata template system — customizable fields per item type. Your manifests have a fixed schema; Tropy lets you define different templates for different kinds of material (photos vs. documents vs. letters). Also interesting: how they handle the relationship between a physical archival item, the photo of it, and the researcher's annotations about it — three layers, like yours.

**Relevance to Living Archive:** Medium. The metadata template concept could inform how you handle the red book (族譜) and elder interview recordings, which need different fields than scanned photos.

### AI-Searchable Family Video Archive (Google Cloud Blog)

A personal project documented on the Google Cloud Blog: one person building an AI-searchable archive for 30 years of family videos using cloud AI services.

- **Blog post:** https://cloud.google.com/blog/products/ai-machine-learning/building-an-ai-searchable-archive-for-30-years-of-family-videos

**What to study:** A kindred project — different tech stack (Google Cloud vs. your NAS + Claude), but the same motivation: one person using AI to make a family media collection searchable. Compare their approach to yours. They went cloud-native; you went local-first. Both are valid. The blog post itself is also a reference for how to write about this kind of project.

**Relevance to Living Archive:** Motivation and presentation reference. Shows there's an audience for this kind of write-up.

---

## Storytelling & Methodology Communication

### Library of Congress — Personal Digital Archiving

The LOC maintains resources specifically for individuals (not institutions) doing personal and family digital preservation.

- **Personal Archiving portal:** https://digitalpreservation.gov/personalarchiving/
- **Resource kit:** https://digitalpreservation.gov/personalarchiving/padKit/resources.html

**What to study:** Framing. The LOC's personal archiving resources show how professionals explain preservation concepts to non-technical audiences. Their "Personal Archiving Day" events are exactly the kind of community outreach your blog series could participate in. If "methodology adopted by at least one other family" is a real success criterion, this is the community to connect with.

**Relevance to Living Archive:** High for content strategy. The LOC has already built the vocabulary and audience for what you're writing about.

### digiKam

Open-source photo management with AI-powered face recognition, metadata enrichment, and batch processing. Desktop application, runs locally.

- **Site:** https://www.digikam.org

**What to study:** Their approach to AI metadata enrichment and face tagging — built into the app rather than as a pipeline. Contrast with your approach (external pipeline writing to an AI layer). digiKam modifies the photos themselves (XMP sidecars or embedded EXIF); you keep metadata separate. Both are defensible, but understanding the trade-offs sharpens your methodology writing.

**Relevance to Living Archive:** Comparison reference. Useful for blog posts explaining *why* you chose a pipeline approach over an all-in-one tool.

---

## How to Use This Document

This isn't a checklist. Pick references based on what you're working on:

- **Hardening the data layer?** Start with NDSA Levels for self-assessment, then BagIt if you want formal packaging.
- **Designing access controls?** Study Mukurtu's cultural protocols.
- **Writing the first blog post?** Read the Pudding for structure, the LOC personal archiving resources for framing, and the Google Cloud family video post for a peer example.
- **Building the development dashboard?** Look at Omeka S's admin/public split and Archivematica's web-based ingest monitoring for UI patterns.
- **Preparing for the personal data branch?** PhotoStructure for dedup patterns, Perkeep for content-addressed architecture at scale.
