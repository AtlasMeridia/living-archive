"""Security regression tests for NAS preflight mounting."""

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

from src import preflight


def _prepare_unmounted(monkeypatch):
    monkeypatch.setattr(preflight, "_expected_mount_usable", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(preflight.time, "sleep", lambda _seconds: None)


def test_mount_uses_secret_stdin_without_putting_password_in_command(tmp_path, monkeypatch):
    _prepare_unmounted(monkeypatch)
    calls = []
    sentinel = "DO-NOT-PUT-THIS-SECRET-IN-ARGV"

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == preflight.AGENT_SECRET_BIN:
            return SimpleNamespace(returncode=0, stdout=sentinel)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)

    assert not preflight.ensure_nas_mounted(
        tmp_path / "not-mounted",
        mount_attempts=1,
    )

    assert len(calls) == 2
    secret_command, _ = calls[0]
    assert secret_command == [
        preflight.AGENT_SECRET_BIN,
        "get",
        "MNEME Living Archive Read-Only",
        "--field",
        "password",
    ]
    secret_env = calls[0][1]["env"]
    assert secret_env["PATH"].split(":")[:2] == [
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    command, kwargs = calls[1]
    rendered = " ".join(command)
    assert command == ["/usr/bin/osascript", "-"]
    assert "security" not in rendered
    assert sentinel not in rendered
    assert sentinel in kwargs["input"]
    assert 'as user name "living_archive_ro"' in kwargs["input"]
    assert 'mount volume "smb://mneme.local/MNEME"' in kwargs["input"]
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_malformed_mount_config_never_reaches_subprocess_or_logs_value(
    tmp_path,
    monkeypatch,
    caplog,
):
    _prepare_unmounted(monkeypatch)
    sentinel = 'user:DO-NOT-LOG-THIS-SECRET@host" & do shell script "bad"'
    monkeypatch.setattr(preflight, "NAS_USER", sentinel)
    calls = []
    monkeypatch.setattr(preflight.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    caplog.set_level(logging.WARNING, logger="living_archive")

    assert not preflight.ensure_nas_mounted(
        tmp_path / "not-mounted",
        mount_attempts=1,
    )

    assert calls == []
    assert sentinel not in caplog.text
    assert "contains invalid characters" in caplog.text


def test_timeout_details_cannot_leak_to_logs(tmp_path, monkeypatch, caplog):
    _prepare_unmounted(monkeypatch)
    sentinel = "DO-NOT-LOG-THIS-SECRET"

    def fake_run(command, **_kwargs):
        if command[0] == preflight.AGENT_SECRET_BIN:
            return SimpleNamespace(returncode=0, stdout=sentinel)
        raise subprocess.TimeoutExpired(command, 30, stderr=sentinel)

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    caplog.set_level(logging.WARNING, logger="living_archive")

    assert not preflight.ensure_nas_mounted(
        tmp_path / "not-mounted",
        mount_attempts=1,
    )

    assert sentinel not in caplog.text
    assert "timed out after 30 seconds" in caplog.text


def test_failed_command_stderr_cannot_leak_to_logs(tmp_path, monkeypatch, caplog):
    _prepare_unmounted(monkeypatch)
    sentinel = "DO-NOT-LOG-THIS-SECRET"

    def fake_run(command, **_kwargs):
        if command[0] == preflight.AGENT_SECRET_BIN:
            return SimpleNamespace(returncode=0, stdout=sentinel)
        return SimpleNamespace(returncode=77, stderr=sentinel)

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    caplog.set_level(logging.WARNING, logger="living_archive")

    assert not preflight.ensure_nas_mounted(
        tmp_path / "not-mounted",
        mount_attempts=1,
    )

    assert sentinel not in caplog.text
    assert "failed (exit 77)" in caplog.text


def test_secret_lookup_failure_details_cannot_leak_to_logs(tmp_path, monkeypatch, caplog):
    _prepare_unmounted(monkeypatch)
    sentinel = "DO-NOT-LOG-SECRET-STORE-OUTPUT"

    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda _command, **_kwargs: SimpleNamespace(returncode=1, stdout=sentinel),
    )
    caplog.set_level(logging.WARNING, logger="living_archive")

    assert not preflight.ensure_nas_mounted(
        tmp_path / "not-mounted",
        mount_attempts=1,
    )

    assert sentinel not in caplog.text
    assert "credential unavailable" in caplog.text


def test_secret_lookup_preserves_boundary_whitespace(monkeypatch):
    sentinel = " leading-and-trailing-space "
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda _command, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=f"{sentinel}\n",
        ),
    )

    assert preflight._get_nas_password() == sentinel


def test_mount_identity_requires_expected_user_host_share_and_smb(tmp_path, monkeypatch):
    volumes = tmp_path / "Volumes"
    media = volumes / "MNEME-1" / "Family" / "Media"
    media.mkdir(parents=True)

    def mount_result(source, filesystem="smbfs"):
        return SimpleNamespace(
            returncode=0,
            stdout=f"{source} on {volumes / 'MNEME-1'} ({filesystem}, nodev)\n",
        )

    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: mount_result(
            "//living_archive_ro@mneme.local/MNEME"
        ),
    )
    assert preflight._mount_identity_matches(media, volumes)

    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: mount_result("//mneme_admin@mneme.local/MNEME"),
    )
    assert not preflight._mount_identity_matches(media, volumes)

    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: mount_result(
            "//living_archive_ro@other.local/MNEME"
        ),
    )
    assert not preflight._mount_identity_matches(media, volumes)

    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: mount_result(
            "//living_archive_ro@mneme.local/MNEME",
            filesystem="apfs",
        ),
    )
    assert not preflight._mount_identity_matches(media, volumes)


def test_resolves_finder_volume_alias_and_rebinds_config(tmp_path, monkeypatch):
    volumes = tmp_path / "Volumes"
    stale_volume = volumes / "MNEME"
    mounted_volume = volumes / "MNEME-1"
    original_media = stale_volume / "Family" / "Media"
    aliased_media = mounted_volume / "Family" / "Media"
    stale_volume.mkdir(parents=True)
    aliased_media.mkdir(parents=True)
    monkeypatch.setattr(
        preflight,
        "_mount_identity_matches",
        lambda *_args, **_kwargs: True,
    )

    monkeypatch.setattr(preflight.config, "FAMILY_ROOT", stale_volume / "Family")
    monkeypatch.setattr(preflight.config, "MEDIA_ROOT", original_media)
    monkeypatch.setattr(
        preflight.config,
        "DOCUMENTS_ROOT",
        stale_volume / "Family" / "Documents",
    )

    resolved = preflight._resolve_usable_mount_path(original_media, volumes_dir=volumes)

    assert resolved == aliased_media
    assert preflight.config.FAMILY_ROOT == mounted_volume / "Family"
    assert preflight.config.MEDIA_ROOT == aliased_media
    assert preflight.config.DOCUMENTS_ROOT == mounted_volume / "Family" / "Documents"


def test_resolves_stale_alias_to_a_later_alias(tmp_path, monkeypatch):
    volumes = tmp_path / "Volumes"
    stale_volume = volumes / "MNEME-1"
    mounted_volume = volumes / "MNEME-2"
    stale_media = stale_volume / "Family" / "Media"
    mounted_media = mounted_volume / "Family" / "Media"
    stale_volume.mkdir(parents=True)
    mounted_media.mkdir(parents=True)
    monkeypatch.setattr(
        preflight,
        "_mount_identity_matches",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(preflight.config, "MEDIA_ROOT", stale_media)

    resolved = preflight._resolve_usable_mount_path(stale_media, volumes_dir=volumes)

    assert resolved == mounted_media
    assert preflight.config.MEDIA_ROOT == mounted_media
