"""Tests for convert.py: file discovery, preparation, and SHA-256 hashing."""

from PIL import Image

from src.convert import find_photos, needs_conversion, prepare_for_analysis, sha256_file


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


def _make_image(path, size=(100, 80)):
    """Helper: create a minimal image file at the given path."""
    img = Image.new("RGB", size, color="red")
    fmt = "TIFF" if path.suffix.lower() in (".tif", ".tiff") else "JPEG"
    img.save(path, fmt)


class TestFindPhotos:
    def test_finds_tiffs_and_jpegs(self, tmp_path):
        """Should discover both TIFF and JPEG files."""
        _make_image(tmp_path / "a.tif")
        _make_image(tmp_path / "b.jpg")
        _make_image(tmp_path / "c.tiff")
        _make_image(tmp_path / "d.jpeg")
        (tmp_path / "e.png").write_bytes(b"not a match")

        result = find_photos(tmp_path)
        names = [p.name for p in result]
        assert "a.tif" in names
        assert "b.jpg" in names
        assert "c.tiff" in names
        assert "d.jpeg" in names
        assert "e.png" not in names

    def test_finds_only_jpegs(self, tmp_path):
        """Should work when directory contains only JPEGs."""
        _make_image(tmp_path / "photo1.jpg")
        _make_image(tmp_path / "photo2.jpeg")

        result = find_photos(tmp_path)
        assert len(result) == 2
        names = [p.name for p in result]
        assert "photo1.jpg" in names
        assert "photo2.jpeg" in names

    def test_empty_directory(self, tmp_path):
        """Should return empty list for directory with no photos."""
        (tmp_path / "readme.txt").write_text("nothing here")
        assert find_photos(tmp_path) == []

    def test_returns_sorted(self, tmp_path):
        """Results should be sorted by path."""
        _make_image(tmp_path / "z.jpg")
        _make_image(tmp_path / "a.tif")
        _make_image(tmp_path / "m.jpeg")

        result = find_photos(tmp_path)
        assert result == sorted(result)


class TestNeedsConversion:
    def test_tiff_always_needs_conversion(self, tmp_path):
        """TIFFs always need conversion regardless of size."""
        small_tiff = tmp_path / "small.tif"
        _make_image(small_tiff, size=(100, 100))
        assert needs_conversion(small_tiff) is True

    def test_small_jpeg_no_conversion(self, tmp_path):
        """JPEGs under MAX_EDGE should not need conversion."""
        small_jpg = tmp_path / "small.jpg"
        _make_image(small_jpg, size=(1024, 768))
        assert needs_conversion(small_jpg) is False

    def test_large_jpeg_needs_conversion(self, tmp_path):
        """JPEGs over MAX_EDGE should need resizing."""
        large_jpg = tmp_path / "large.jpg"
        _make_image(large_jpg, size=(4000, 3000))
        assert needs_conversion(large_jpg) is True

    def test_mislabeled_tiff_with_jpeg_extension_needs_conversion(self, tmp_path):
        """Files in JPEG folders can actually contain TIFF bytes and must be normalized."""
        disguised = tmp_path / "scan.jpeg"
        img = Image.new("RGB", (1200, 1600), color="red")
        img.save(disguised, "TIFF")

        assert needs_conversion(disguised) is True


class TestPrepareForAnalysis:
    def test_tiff_to_jpeg(self, tmp_path):
        """Should convert TIFF to JPEG."""
        src = tmp_path / "input.tif"
        dst = tmp_path / "output.jpg"
        _make_image(src, size=(200, 150))

        prepare_for_analysis(src, dst)

        assert dst.exists()
        with Image.open(dst) as img:
            assert img.format == "JPEG"

    def test_jpeg_to_jpeg(self, tmp_path):
        """Should handle JPEG input (re-save as JPEG)."""
        src = tmp_path / "input.jpg"
        dst = tmp_path / "output.jpg"
        _make_image(src, size=(200, 150))

        prepare_for_analysis(src, dst)

        assert dst.exists()
        with Image.open(dst) as img:
            assert img.format == "JPEG"

    def test_resizes_large_image(self, tmp_path):
        """Should resize images with longest edge > MAX_EDGE."""
        src = tmp_path / "big.tif"
        dst = tmp_path / "small.jpg"
        _make_image(src, size=(4000, 3000))

        prepare_for_analysis(src, dst)

        with Image.open(dst) as img:
            assert max(img.size) <= 2048

    def test_preserves_small_image(self, tmp_path):
        """Should not resize images already under MAX_EDGE."""
        src = tmp_path / "ok.jpg"
        dst = tmp_path / "out.jpg"
        _make_image(src, size=(1024, 768))

        prepare_for_analysis(src, dst)

        with Image.open(dst) as img:
            # Dimensions may differ slightly due to JPEG re-encoding,
            # but should not be resized down
            assert max(img.size) <= 2048
            assert max(img.size) >= 1000  # not aggressively resized

    def test_creates_parent_dirs(self, tmp_path):
        """Should create parent directories if they don't exist."""
        src = tmp_path / "input.tif"
        dst = tmp_path / "sub" / "dir" / "output.jpg"
        _make_image(src, size=(200, 150))

        prepare_for_analysis(src, dst)

        assert dst.exists()
