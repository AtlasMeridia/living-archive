
import json
import os
import argparse
from datetime import datetime, timezone
import collections
import re
import shutil

# --- Helper Functions ---

def normalize_timestamp(timestamp_str):
    if not timestamp_str:
        return None
    try:
        # datetime.fromisoformat can handle various ISO 8601 formats including Z and offset
        dt_obj = datetime.fromisoformat(timestamp_str)
        # Ensure it's UTC and format consistently
        if dt_obj.tzinfo is None:
            # Assume naive timestamps are UTC unless specified otherwise
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        return dt_obj.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    except ValueError:
        return None

def stat_file_info(file_path, project_root):
    absolute_path = os.path.join(project_root, file_path)
    try:
        stat_info = os.stat(absolute_path)
        mtime = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        return stat_info.st_size, mtime
    except FileNotFoundError:
        print(f"WARNING: Source file not found: {absolute_path}")
        return None, None
    except OSError as e:
        print(f"WARNING: Could not stat file {absolute_path}: {e}")
        return None, None

def extract_people_from_notes(notes):
    if not notes:
        return []
    # Simple regex to find quoted names (e.g., "John Doe")
    return re.findall(r'"([^"]*)"', notes)

def wrap_with_authority(value, authority="machine"):
    """Wrap a value for interpretation partition, injecting 'authority'.

    Rules:
    - None → None
    - dict without 'authority' → inject 'authority' key directly
    - dict with 'authority' → return as-is (already wrapped)
    - list → wrap as {"values": [...], "authority": ...}
    - scalar → wrap as {"value": ..., "authority": ...}
    """
    if value is None:
        return None
    if isinstance(value, dict):
        if "authority" in value:
            return value  # Already wrapped
        result = dict(value, authority=authority)
        return result
    if isinstance(value, list):
        return {"values": value, "authority": authority}
    return {"value": value, "authority": authority}


# --- Migration Logic ---

def _add_provenance(v2_manifest, v1_manifest, agent, run_id, fields_written):
    """Add provenance partition from v1 inference data."""
    inference = v1_manifest.get("inference", {})
    if inference:
        input_tokens = inference.get('estimated_input_tokens') or inference.get('input_tokens')
        v2_manifest["provenance"]["history"] = [{
            "run_id": run_id,
            "timestamp": normalize_timestamp(inference.get("timestamp")),
            "agent": agent,
            "model": inference.get("model"),
            "prompt_version": inference.get("prompt_version"),
            "input_tokens": input_tokens,
            "output_tokens": inference.get("output_tokens"),
            "fields_written": fields_written
        }]
        v2_manifest["provenance"]["created_at"] = normalize_timestamp(inference.get("timestamp"))
        v2_manifest["provenance"]["updated_at"] = normalize_timestamp(inference.get("timestamp"))
    else:
        now_iso = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        v2_manifest["provenance"]["history"] = [{
            "run_id": run_id,
            "timestamp": now_iso,
            "agent": "migration.v1_to_v2",
            "model": "unknown",
            "prompt_version": "n/a",
            "input_tokens": 0,
            "output_tokens": 0,
            "fields_written": fields_written
        }]
        v2_manifest["provenance"]["created_at"] = now_iso
        v2_manifest["provenance"]["updated_at"] = now_iso


def migrate_photo_manifest(v1_manifest, project_root, run_id):
    v2_manifest = {
        "source": {},
        "technical": {},
        "interpretation": {},
        "provenance": {}
    }
    fields_written = []

    # Source
    v2_manifest["source"]["path"] = v1_manifest["source_file"]
    v2_manifest["source"]["sha256"] = v1_manifest["source_sha256"]
    v2_manifest["source"]["media_type"] = "photo"
    file_size, file_mtime = stat_file_info(v1_manifest["source_file"], project_root)
    v2_manifest["source"]["file_size"] = file_size
    v2_manifest["source"]["file_mtime"] = file_mtime
    fields_written.extend([
        "source.path", "source.sha256", "source.media_type",
        "source.file_size", "source.file_mtime"
    ])

    # Technical
    # V1 photos don't have width/height/rotation/derivative_path
    v2_manifest["technical"]["rotation"] = 0 # Default for photos if not present
    fields_written.append("technical.rotation")

    # Interpretation
    analysis = v1_manifest.get("analysis", {})

    caption_en = analysis.get("description_en")
    caption_zh = analysis.get("description_zh")
    if caption_en or caption_zh:
        caption_data = {}
        if caption_en:
            caption_data["en"] = caption_en
        if caption_zh:
            caption_data["zh"] = caption_zh
        v2_manifest["interpretation"]["caption"] = wrap_with_authority(caption_data)
        fields_written.append("interpretation.caption")

    if "date_estimate" in analysis:
        v2_manifest["interpretation"]["date"] = wrap_with_authority({
            "estimate": analysis.get("date_estimate"),
            "precision": analysis.get("date_precision"),
            "confidence": analysis.get("date_confidence"),
            "reasoning": analysis.get("date_reasoning"),
        })
        fields_written.append("interpretation.date")

    people_count = analysis.get("people_count")
    people_notes = analysis.get("people_notes")
    if people_count is not None or people_notes:
        v2_manifest["interpretation"]["people"] = wrap_with_authority({
            "count": people_count,
            "notes": people_notes,
            "identified": extract_people_from_notes(people_notes),
            "person_ids": [], # V1 has no person IDs
        })
        fields_written.append("interpretation.people")

    if "location_estimate" in analysis:
        v2_manifest["interpretation"]["location"] = wrap_with_authority({
            "estimate": analysis.get("location_estimate"),
            "confidence": analysis.get("location_confidence"),
        })
        fields_written.append("interpretation.location")

    if "tags" in analysis:
        v2_manifest["interpretation"]["tags"] = wrap_with_authority(analysis["tags"])
        fields_written.append("interpretation.tags")

    if "condition_notes" in analysis:
        v2_manifest["interpretation"]["condition"] = wrap_with_authority({
            "notes": analysis["condition_notes"],
        })
        fields_written.append("interpretation.condition")

    if "ocr_text" in analysis and analysis["ocr_text"]:
        v2_manifest["interpretation"]["ocr_text"] = wrap_with_authority(analysis["ocr_text"])
        fields_written.append("interpretation.ocr_text")

    # Provenance
    _add_provenance(v2_manifest, v1_manifest, "pipeline.photo", run_id, fields_written)

    return v2_manifest

def migrate_document_manifest(v1_manifest, project_root, run_id):
    v2_manifest = {
        "source": {},
        "technical": {},
        "interpretation": {},
        "provenance": {}
    }
    fields_written = []

    # Source
    v2_manifest["source"]["path"] = v1_manifest["source_file"]
    v2_manifest["source"]["sha256"] = v1_manifest["source_sha256"]
    v2_manifest["source"]["media_type"] = "document"
    # stat source file for file_size/file_mtime
    # source path is relative to project NAS mount, prepend project_root
    file_size, file_mtime = stat_file_info(v1_manifest["source_file"], project_root)
    v2_manifest["source"]["file_size"] = file_size
    v2_manifest["source"]["file_mtime"] = file_mtime
    fields_written.extend([
        "source.path", "source.sha256", "source.media_type",
        "source.file_size", "source.file_mtime"
    ])

    # Technical
    extraction = v1_manifest.get("extraction", {})
    if "page_count" in v1_manifest:
        v2_manifest["technical"]["page_count"] = v1_manifest["page_count"]
        fields_written.append("technical.page_count")
    if "chars_extracted" in extraction:
        v2_manifest["technical"]["chars_extracted"] = extraction["chars_extracted"]
        fields_written.append("technical.chars_extracted")
    if extraction.get("text_file"):
        text_path = extraction["text_file"]
        # Strip "extracted-text/" prefix if present since v2 paths are relative to synthesis/
        if text_path.startswith("extracted-text/"):
            text_path = text_path[len("extracted-text/"):]
        v2_manifest["technical"]["text_path"] = text_path
        fields_written.append("technical.text_path")

    # Interpretation
    analysis = v1_manifest.get("analysis", {})

    if "title" in analysis:
        v2_manifest["interpretation"]["caption"] = wrap_with_authority({
            "en": analysis["title"]
        })
        fields_written.append("interpretation.caption")

    if "date" in analysis or "date_confidence" in analysis:
        date_obj = {
            "estimate": analysis.get("date"),
            "precision": analysis.get("date_precision"),  # Not in v1 docs, may be None
            "confidence": analysis.get("date_confidence"),
            "reasoning": None,  # Not in v1
        }
        v2_manifest["interpretation"]["date"] = wrap_with_authority(date_obj)
        fields_written.append("interpretation.date")

    key_people = analysis.get("key_people")
    if key_people:
        v2_manifest["interpretation"]["people"] = wrap_with_authority({
            "identified": key_people,
            "count": len(key_people),
            "notes": None,
            "person_ids": [],
        })
        fields_written.append("interpretation.people")

    if "document_type" in analysis:
        v2_manifest["interpretation"]["document_type"] = wrap_with_authority(analysis["document_type"])
        fields_written.append("interpretation.document_type")

    sensitivity = analysis.get("sensitivity")
    if sensitivity:
        v2_manifest["interpretation"]["sensitivity"] = wrap_with_authority(sensitivity)
        fields_written.append("interpretation.sensitivity")

    if "tags" in analysis:
        v2_manifest["interpretation"]["tags"] = wrap_with_authority(analysis["tags"])
        fields_written.append("interpretation.tags")

    summary_en = analysis.get("summary_en")
    summary_zh = analysis.get("summary_zh")
    if summary_en or summary_zh:
        summary_data = {}
        if summary_en:
            summary_data["en"] = summary_en
        if summary_zh:
            summary_data["zh"] = summary_zh
        v2_manifest["interpretation"]["summary"] = wrap_with_authority(summary_data)
        fields_written.append("interpretation.summary")

    if "language" in analysis:
        v2_manifest["interpretation"]["language"] = wrap_with_authority(analysis["language"])
        fields_written.append("interpretation.language")

    if "quality" in analysis:
        v2_manifest["interpretation"]["quality"] = wrap_with_authority(analysis["quality"])
        fields_written.append("interpretation.quality")

    # Provenance
    _add_provenance(v2_manifest, v1_manifest, "pipeline.doc", run_id, fields_written)

    return v2_manifest

# --- Main Migration Process ---

def process_migration(source_dir, dest_dir, project_root, dry_run=False):
    processed_count = 0
    written_count = 0
    skipped_count = 0
    error_count = 0
    
    # Store candidates for deduplication
    manifest_candidates = collections.defaultdict(list) # {sha256: [(timestamp, manifest_dict, original_path)]}

    for root, _, files in os.walk(source_dir):
        if "manifests" in root:
            # Infer media type from path. Example: data/photos/runs/some_run_id/manifests/
            media_type = None
            if "/photos/" in root:
                media_type = "photo"
            elif "/documents/" in root:
                media_type = "document"
            
            if media_type is None:
                print(f"Skipping unknown media type directory: {root}")
                continue

            # Extract run_id from the path. Example: .../runs/20260303T005448Z/manifests/
            run_match = re.search(r'runs/([^/]+)/manifests', root)
            run_id = run_match.group(1) if run_match else "unknown_run"
            
            for f in files:
                if f.endswith(".json"):
                    v1_path = os.path.join(root, f)
                    processed_count += 1
                    try:
                        with open(v1_path, 'r', encoding='utf-8') as infile:
                            v1_manifest = json.load(infile)

                        v2_manifest = None
                        if media_type == "photo":
                            v2_manifest = migrate_photo_manifest(v1_manifest, project_root, run_id)
                        elif media_type == "document":
                            v2_manifest = migrate_document_manifest(v1_manifest, project_root, run_id)
                        
                        if v2_manifest:
                            sha256 = v2_manifest["source"]["sha256"]
                            timestamp_str = (
                                v2_manifest["provenance"]["history"][0]["timestamp"]
                                if v2_manifest["provenance"]["history"] else 
                                datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z') # Fallback if no timestamp
                            )
                            # Convert to datetime object for comparison
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            manifest_candidates[sha256].append((timestamp, v2_manifest, v1_path))

                    except json.JSONDecodeError:
                        print(f"ERROR: Could not decode JSON from {v1_path}")
                        error_count += 1
                    except Exception as e:
                        print(f"ERROR: Processing {v1_path}: {e}")
                        error_count += 1
    
    # Process candidates for deduplication and writing
    for sha256, candidates in manifest_candidates.items():
        # Sort by timestamp (most recent first)
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Keep only the most recent manifest for this SHA256
        most_recent_manifest = candidates[0][1]
        original_v1_path_of_chosen = candidates[0][2]

        # V2 destination path is synthesis/sha256.json
        dest_output_filename = f"{most_recent_manifest['source']['sha256']}.json"
        
        # Determine the correct partition subdirectory for v2
        # Use first two characters of SHA256 for partitioning
        partition_dir = os.path.join(dest_dir, most_recent_manifest["source"]["media_type"] + "s", sha256[:2])
        os.makedirs(partition_dir, exist_ok=True) # Ensure partitioned directory exists

        dest_v2_path = os.path.join(partition_dir, dest_output_filename)

        if dry_run:
            print(f"DRY RUN: Would write V2 manifest for {sha256} to {dest_v2_path}")
            print(f"          (original V1 from {original_v1_path_of_chosen})")
            written_count += 1 # Count as 'would be written'
        else:
            try:
                # Validate SHA256 matches filename
                if most_recent_manifest['source']['sha256'] != os.path.splitext(dest_output_filename)[0]:
                    print(f"ERROR: SHA256 mismatch for {dest_output_filename}. Expected {most_recent_manifest['source']['sha256']}, got {os.path.splitext(dest_output_filename)[0]}")
                    error_count += 1
                    skipped_count += 1
                    continue

                # Atomic write
                temp_file_path = dest_v2_path + ".tmp"
                with open(temp_file_path, 'w', encoding='utf-8') as outfile:
                    json.dump(most_recent_manifest, outfile, indent=2, ensure_ascii=False)
                os.rename(temp_file_path, dest_v2_path)
                written_count += 1
            except Exception as e:
                print(f"ERROR: Writing V2 manifest for {sha256} to {dest_v2_path}: {e}")
                error_count += 1
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
        
        # Everything else for this SHA256 is skipped due to deduplication
        skipped_count += (len(candidates) - 1)
    
    return processed_count, written_count, skipped_count, error_count

def main():
    parser = argparse.ArgumentParser(description="Migrate v1 manifests to v2 partitioned format.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing files.")
    parser.add_argument("--source", type=str, default="data/", help="Source directory for v1 manifests (default: data/).")
    parser.add_argument("--dest", type=str, default="synthesis/", help="Destination directory for v2 manifests (default: synthesis/).")
    
    args = parser.parse_args()

    project_root = "/Users/atlas/Projects/living-archive" # Base path for stat() calls
    source_absolute_path = os.path.join(project_root, args.source)
    dest_absolute_path = os.path.join(project_root, args.dest)

    os.makedirs(dest_absolute_path, exist_ok=True)

    print(f"Starting v1 to v2 migration from '{source_absolute_path}' to '{dest_absolute_path}'.")
    if args.dry_run:
        print("Running in DRY-RUN mode. No files will be written.")

    processed, written, skipped, errors = process_migration(
        source_absolute_path, dest_absolute_path, project_root, args.dry_run
    )

    print("\n--- Migration Summary ---")
    print(f"Manifests processed: {processed}")
    print(f"Manifests written:   {written}")
    print(f"Manifests skipped:   {skipped} (due to deduplication or errors)")
    print(f"Errors encountered:  {errors}")

if __name__ == "__main__":
    main()
