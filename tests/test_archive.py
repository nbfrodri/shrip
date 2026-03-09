"""Tests for shrip.archive module."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from shrip.archive import create_archive, sanitize_name


# ── Helpers ──────────────────────────────────────────────────────────────────


def _zip_names(zip_path: Path) -> list[str]:
    """Return sorted list of entry names in a zip file."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        return sorted(zf.namelist())


# ── sanitize_name ────────────────────────────────────────────────────────────


class TestSanitizeName:
    def test_strips_zip_extension(self):
        assert sanitize_name("archive.zip") == "archive"

    def test_removes_dangerous_chars(self):
        assert sanitize_name('my:file*name?"<>|') == "myfilename"

    def test_replaces_spaces_with_underscores(self):
        assert sanitize_name("my archive name") == "my_archive_name"

    def test_strips_slashes(self):
        assert sanitize_name("path/to\\name") == "pathtoname"

    def test_empty_after_sanitize_returns_default(self):
        assert sanitize_name("***") == "shrip_archive"

    def test_strips_leading_dots_and_underscores(self):
        assert sanitize_name("...__name") == "name"

    def test_normal_name_unchanged(self):
        assert sanitize_name("v1-handover") == "v1-handover"


# ── create_archive: single file ─────────────────────────────────────────────


class TestSingleFile:
    def test_single_file(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello")

        zip_path = create_archive([f], "test")
        try:
            names = _zip_names(zip_path)
            assert names == ["hello.txt"]
            with zipfile.ZipFile(zip_path) as zf:
                assert zf.read("hello.txt") == b"hello"
        finally:
            zip_path.unlink(missing_ok=True)

    def test_single_file_default_name(self, tmp_path: Path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")

        zip_path = create_archive([f])
        try:
            assert ".shrip_shrip_archive_" in zip_path.name
        finally:
            zip_path.unlink(missing_ok=True)


# ── create_archive: single directory ────────────────────────────────────────


class TestSingleDirectory:
    def test_flat_directory(self, tmp_path: Path):
        d = tmp_path / "mydir"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")

        zip_path = create_archive([d], "test")
        try:
            names = _zip_names(zip_path)
            assert names == ["mydir/a.txt", "mydir/b.txt"]
        finally:
            zip_path.unlink(missing_ok=True)

    def test_nested_directory(self, tmp_path: Path):
        d = tmp_path / "project"
        (d / "src" / "utils").mkdir(parents=True)
        (d / "src" / "main.py").write_text("main")
        (d / "src" / "utils" / "helper.py").write_text("helper")
        (d / "README.md").write_text("readme")

        zip_path = create_archive([d], "test")
        try:
            names = _zip_names(zip_path)
            assert "project/README.md" in names
            assert "project/src/main.py" in names
            assert "project/src/utils/helper.py" in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_empty_directory(self, tmp_path: Path):
        d = tmp_path / "emptydir"
        d.mkdir()

        zip_path = create_archive([d], "test")
        try:
            names = _zip_names(zip_path)
            assert names == ["emptydir/"]
        finally:
            zip_path.unlink(missing_ok=True)


# ── create_archive: mixed inputs ────────────────────────────────────────────


class TestMixedInputs:
    def test_file_and_directory(self, tmp_path: Path):
        f = tmp_path / "standalone.txt"
        f.write_text("standalone")

        d = tmp_path / "folder"
        d.mkdir()
        (d / "inside.txt").write_text("inside")

        zip_path = create_archive([f, d], "mixed")
        try:
            names = _zip_names(zip_path)
            assert "standalone.txt" in names
            assert "folder/inside.txt" in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_multiple_directories(self, tmp_path: Path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        (d1 / "a.txt").write_text("a")

        d2 = tmp_path / "dir2"
        d2.mkdir()
        (d2 / "b.txt").write_text("b")

        zip_path = create_archive([d1, d2], "multi")
        try:
            names = _zip_names(zip_path)
            assert "dir1/a.txt" in names
            assert "dir2/b.txt" in names
        finally:
            zip_path.unlink(missing_ok=True)


# ── create_archive: duplicate filenames ──────────────────────────────────────


class TestDuplicateNames:
    def test_duplicate_files_get_unique_arcnames(self, tmp_path: Path):
        d1 = tmp_path / "a"
        d1.mkdir()
        f1 = d1 / "readme.txt"
        f1.write_text("first")

        d2 = tmp_path / "b"
        d2.mkdir()
        f2 = d2 / "readme.txt"
        f2.write_text("second")

        zip_path = create_archive([f1, f2], "dupes")
        try:
            names = _zip_names(zip_path)
            assert len(names) == 2
            # Both files present, one got deduplicated
            assert "readme.txt" in names
            assert "readme_2.txt" in names
        finally:
            zip_path.unlink(missing_ok=True)


# ── create_archive: name sanitization ───────────────────────────────────────


class TestNameSanitization:
    def test_name_with_zip_extension(self, tmp_path: Path):
        f = tmp_path / "x.txt"
        f.write_text("x")

        zip_path = create_archive([f], "myarchive.zip")
        try:
            assert ".shrip_myarchive_" in zip_path.name
        finally:
            zip_path.unlink(missing_ok=True)

    def test_name_with_special_chars(self, tmp_path: Path):
        f = tmp_path / "x.txt"
        f.write_text("x")

        zip_path = create_archive([f], 'bad:*name?"')
        try:
            assert ".shrip_badname_" in zip_path.name
        finally:
            zip_path.unlink(missing_ok=True)


# ── create_archive: error cases ─────────────────────────────────────────────


class TestErrors:
    def test_nonexistent_path(self, tmp_path: Path):
        bad = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="does_not_exist"):
            create_archive([bad], "test")

    def test_nonexistent_among_valid(self, tmp_path: Path):
        good = tmp_path / "good.txt"
        good.write_text("ok")
        bad = tmp_path / "nope.txt"

        with pytest.raises(FileNotFoundError, match="nope"):
            create_archive([good, bad], "test")

    def test_cleanup_on_nonexistent_leaves_no_temp(self, tmp_path: Path):
        """Ensure no temp zip is left behind when validation fails."""
        bad = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError):
            create_archive([bad], "test")
        # No .shrip_ temp files should exist in the temp directory
        import tempfile

        temps = list(Path(tempfile.gettempdir()).glob(".shrip_test_*"))
        # Filter to only recent ones (avoid collisions with other test runs)
        assert len(temps) == 0


# ── create_archive: progress callback ───────────────────────────────────────


class TestProgressCallback:
    def test_callback_called_for_each_file(self, tmp_path: Path):
        d = tmp_path / "cbdir"
        d.mkdir()
        (d / "one.txt").write_text("1")
        (d / "two.txt").write_text("2")

        f = tmp_path / "three.txt"
        f.write_text("3")

        called_with: list[Path] = []
        zip_path = create_archive([d, f], "cb", progress_callback=called_with.append)
        try:
            assert len(called_with) == 3
        finally:
            zip_path.unlink(missing_ok=True)

    def test_callback_none_is_fine(self, tmp_path: Path):
        f = tmp_path / "ok.txt"
        f.write_text("ok")

        zip_path = create_archive([f], "nocb", progress_callback=None)
        try:
            assert zip_path.exists()
        finally:
            zip_path.unlink(missing_ok=True)


# ── create_archive: symlinks ────────────────────────────────────────────────


class TestSymlinks:
    def test_symlink_inside_tree_is_included(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        real = d / "real.txt"
        real.write_text("real")
        link = d / "link.txt"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        zip_path = create_archive([d], "sym")
        try:
            names = _zip_names(zip_path)
            assert "proj/real.txt" in names
            assert "proj/link.txt" in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_symlink_outside_tree_is_skipped(self, tmp_path: Path):
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")

        d = tmp_path / "proj"
        d.mkdir()
        (d / "safe.txt").write_text("safe")
        link = d / "escape.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        zip_path = create_archive([d], "sym")
        try:
            names = _zip_names(zip_path)
            assert "proj/safe.txt" in names
            assert "proj/escape.txt" not in names
        finally:
            zip_path.unlink(missing_ok=True)
