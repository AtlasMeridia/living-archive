"""Permission tests for private application logging."""

import logging
import os
import stat

from src import config


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_setup_logging_restricts_private_directory_and_logs(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir(mode=0o755)
    current = private / "living-archive.log"
    rotated = private / "living-archive.log.1"
    current.write_text("current")
    rotated.write_text("rotated")
    os.chmod(private, 0o755)
    os.chmod(current, 0o644)
    os.chmod(rotated, 0o644)

    logger = logging.getLogger("living_archive")
    original_handlers = list(logger.handlers)
    for handler in original_handlers:
        logger.removeHandler(handler)

    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    try:
        configured = config.setup_logging()
        configured.info("permission check")
        for handler in configured.handlers:
            handler.flush()

        assert _mode(private) == 0o700
        assert _mode(current) == 0o600
        assert _mode(rotated) == 0o600
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            logger.addHandler(handler)


def test_rotated_file_handler_creates_owner_only_files(tmp_path):
    path = tmp_path / "application.log"
    handler = config.PrivateRotatingFileHandler(path, maxBytes=1, backupCount=1)
    try:
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.emit(logging.makeLogRecord({"msg": "first"}))
        handler.doRollover()
        handler.emit(logging.makeLogRecord({"msg": "second"}))
    finally:
        handler.close()

    assert _mode(path) == 0o600
    assert _mode(tmp_path / "application.log.1") == 0o600
