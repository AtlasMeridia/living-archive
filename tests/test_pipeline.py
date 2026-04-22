"""Tests for run_batch: run-scoped workspaces and cleanup tolerance."""

from PIL import Image

import src.config as config
from src.pipeline import process_slice


def test_process_slice_uses_run_scoped_workspace_and_tolerates_cleanup_errors(tmp_path, monkeypatch):
    """Per-run workspaces avoid collisions, and cleanup failures should not abort the slice result."""
    album_dir = tmp_path / "album"
    album_dir.mkdir()
    src = album_dir / "scan.jpeg"
    Image.new("RGB", (100, 100), color="blue").save(src, "JPEG")

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(config, "AI_LAYER_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "workspace-root")
    monkeypatch.setattr("src.pipeline.find_photos", lambda _: [src])
    monkeypatch.setattr("src.pipeline.needs_conversion", lambda _: False)

    captured = {}

    def fake_copy2(source, dest):
        dest.write_bytes(source.read_bytes())
        captured["copied_to"] = dest
        return dest

    monkeypatch.setattr("src.pipeline.shutil.copy2", fake_copy2)
    monkeypatch.setattr(
        "src.pipeline.analyze_photo",
        lambda jpeg_path, folder_hint: (_ for _ in ()).throw(RuntimeError(f"saw:{jpeg_path}")),
    )
    monkeypatch.setattr("src.pipeline._cleanup_workspace", lambda workspace: (_ for _ in ()).throw(OSError("busy")))

    result = process_slice(
        slice_path="album",
        slice_dir=album_dir,
        run_id="20260304T000000Z",
        budget_remaining=3600,
        push=False,
    )

    assert captured["copied_to"].parent != config.WORKSPACE_DIR
    assert "20260304T000000Z" in str(captured["copied_to"].parent)
    assert result["failed"] == 1
    assert result["succeeded"] == 0
