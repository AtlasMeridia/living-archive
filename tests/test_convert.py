"""Tests for convert.py: SHA-256 hashing."""

from src.convert import sha256_file


class TestSha256File:
    def test_known_content(self, tmp_path):
        """SHA-256 of known content should match expected hash."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = sha256_file(f)
        # SHA-256 of "hello world" (no trailing newline)
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_empty_file(self, tmp_path):
        """SHA-256 of empty file should be the known empty-input hash."""
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        result = sha256_file(f)
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_binary_content(self, tmp_path):
        """Should handle binary content correctly."""
        f = tmp_path / "binary.bin"
        f.write_bytes(bytes(range(256)))
        result = sha256_file(f)
        assert len(result) == 64  # SHA-256 hex digest is 64 chars
        assert all(c in "0123456789abcdef" for c in result)
