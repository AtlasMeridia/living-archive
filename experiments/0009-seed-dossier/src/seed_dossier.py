#!/usr/bin/env python3
"""Build a private, read-only seed dossier from existing derived data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from common import BuildOptions
from discovery import build_seed_dossier


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_RUN_ROOT = EXPERIMENT_ROOT / "runs" / "private"


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description=(
            "Discover candidate evidence for one person and period without "
            "modifying Living Archive inputs."
        )
    )
    argument_parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Living Archive project containing the derived data/ inputs",
    )
    argument_parser.add_argument("--subject", required=True, help="Subject seed label")
    argument_parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help="Known name form; repeat for multiple aliases",
    )
    argument_parser.add_argument("--start-year", required=True, type=int)
    argument_parser.add_argument("--end-year", required=True, type=int)
    argument_parser.add_argument(
        "--output-name",
        help="Optional JSON basename inside the experiment's private run directory",
    )
    argument_parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace an existing dossier with the same private output name",
    )
    return argument_parser


def validate_project_root(project_root: Path) -> None:
    data_root = project_root / "data"
    if not data_root.is_dir():
        raise FileNotFoundError(f"derived data directory not found: {data_root}")
    if not (data_root / "catalog.db").is_file():
        raise FileNotFoundError(f"catalog not found: {data_root / 'catalog.db'}")
    manifests = list((data_root / "documents" / "runs").glob("*/manifests/*.json"))
    manifests.extend((data_root / "photos" / "runs").glob("*/manifests/*.json"))
    if not manifests:
        raise FileNotFoundError("no photo or document run manifests were found")


def private_output_path(output_name: str) -> Path:
    if not output_name.endswith(".json"):
        raise ValueError("output name must end in .json")
    if Path(output_name).name != output_name or output_name in {".", ".."}:
        raise ValueError("output name must be a basename inside runs/private")
    if PRIVATE_RUN_ROOT.exists() and PRIVATE_RUN_ROOT.is_symlink():
        raise ValueError("private run directory cannot be a symlink")
    PRIVATE_RUN_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PRIVATE_RUN_ROOT, 0o700)
    root = PRIVATE_RUN_ROOT.resolve(strict=True)
    output = root / output_name
    try:
        output.lstat()
        if output.is_symlink():
            raise ValueError("output cannot replace a symlink")
    except FileNotFoundError:
        pass
    resolved_output = output.resolve(strict=False)
    try:
        resolved_output.relative_to(root)
    except ValueError as error:
        raise ValueError("output path escapes the private run directory") from error
    return output


def atomic_write_json(path: Path, payload: dict, replace_existing: bool = False) -> None:
    if path.exists() and not replace_existing:
        raise FileExistsError(f"private dossier already exists: {path.name}")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
            handle.write("\n")
        if replace_existing:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise FileExistsError(
                    f"private dossier already exists: {path.name}"
                ) from error
            temporary.unlink()
        os.chmod(path, 0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project_root = args.project_root.resolve()
    validate_project_root(project_root)
    aliases = list(args.alias)
    options = BuildOptions(
        subject_label=args.subject,
        aliases=tuple(aliases),
        start_year=args.start_year,
        end_year=args.end_year,
    )
    dossier = build_seed_dossier(project_root, options)
    output_name = args.output_name or f"{dossier['dossier_id']}.json"
    output = private_output_path(output_name)
    atomic_write_json(output, dossier, replace_existing=args.replace_existing)

    safe_summary = {
        "dossier_id": dossier["dossier_id"],
        "output": str(output),
        **dossier["summary"],
        "visibility": dossier["visibility"],
        "human_verified": dossier["human_verified"],
    }
    print(json.dumps(safe_summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
