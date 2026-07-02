"""Small shared utilities."""

import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> Path:
    """Write text to path atomically (temp file + rename).

    Creates parent directories as needed. Returns the path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w") as f:
            f.write(text)
        Path(tmp).rename(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
