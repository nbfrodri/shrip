"""Tests for shrip.archive module."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import pyzipper

from shrip.archive import _is_incompressible, _should_exclude, create_archive, sanitize_name


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

        bytes_reported: list[int] = []
        zip_path = create_archive([d, f], "cb", progress_callback=bytes_reported.append)
        try:
            # Callback reports bytes; total should match input size
            assert len(bytes_reported) >= 3  # at least one call per file
            assert sum(bytes_reported) == 1 + 1 + 1  # "1" + "2" + "3" = 3 bytes
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


# ── Security: arcname safety ────────────────────────────────────────────────


class TestArcnameSecurity:
    def test_no_arcname_starts_with_slash(self, tmp_path: Path):
        d = tmp_path / "mydir"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "file.txt").write_text("data")
        (d / "top.txt").write_text("top")

        zip_path = create_archive([d], "sec")
        try:
            names = _zip_names(zip_path)
            for name in names:
                assert not name.startswith("/"), f"arcname starts with /: {name}"
                assert ".." not in name, f"arcname contains ..: {name}"
        finally:
            zip_path.unlink(missing_ok=True)

    def test_no_arcname_contains_dotdot(self, tmp_path: Path):
        """Ensure deeply nested dirs never produce .. in arcnames."""
        d = tmp_path / "root"
        (d / "a" / "b" / "c").mkdir(parents=True)
        (d / "a" / "b" / "c" / "deep.txt").write_text("deep")

        zip_path = create_archive([d], "deep")
        try:
            names = _zip_names(zip_path)
            for name in names:
                assert ".." not in name, f"arcname contains ..: {name}"
        finally:
            zip_path.unlink(missing_ok=True)


# ── Fast mode (ZIP_STORED) ────────────────────────────────────────────────


class TestFastMode:
    def test_fast_mode_uses_stored(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        zip_path = create_archive([f], "fast_test", fast=True)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                info = zf.getinfo("data.txt")
                assert info.compress_type == zipfile.ZIP_STORED
        finally:
            zip_path.unlink(missing_ok=True)

    def test_default_mode_uses_deflated(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        zip_path = create_archive([f], "deflate_test")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                info = zf.getinfo("data.txt")
                assert info.compress_type == zipfile.ZIP_DEFLATED
        finally:
            zip_path.unlink(missing_ok=True)


# ── Auto-detect incompressible formats ────────────────────────────────────


class TestIncompressibleDetection:
    def test_known_extensions_detected(self):
        for ext in (".iso", ".mp4", ".zip", ".jpg", ".mp3", ".gz", ".mkv"):
            assert _is_incompressible(Path(f"file{ext}")), f"{ext} should be incompressible"

    def test_text_files_not_detected(self):
        for ext in (".txt", ".py", ".json", ".html", ".csv", ".xml"):
            assert not _is_incompressible(Path(f"file{ext}")), f"{ext} should be compressible"

    def test_incompressible_file_uses_stored(self, tmp_path: Path):
        f = tmp_path / "movie.mp4"
        f.write_bytes(b"\x00" * 100)

        zip_path = create_archive([f], "auto_test")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                info = zf.getinfo("movie.mp4")
                assert info.compress_type == zipfile.ZIP_STORED
        finally:
            zip_path.unlink(missing_ok=True)

    def test_compressible_file_uses_deflated(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("print('hello')")

        zip_path = create_archive([f], "auto_test")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                info = zf.getinfo("code.py")
                assert info.compress_type == zipfile.ZIP_DEFLATED
        finally:
            zip_path.unlink(missing_ok=True)

    def test_mixed_dir_uses_per_file_compression(self, tmp_path: Path):
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "readme.txt").write_text("hello")
        (d / "image.jpg").write_bytes(b"\xff\xd8" * 50)

        zip_path = create_archive([d], "mixed_test")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                txt_info = zf.getinfo("mixed/readme.txt")
                jpg_info = zf.getinfo("mixed/image.jpg")
                assert txt_info.compress_type == zipfile.ZIP_DEFLATED
                assert jpg_info.compress_type == zipfile.ZIP_STORED
        finally:
            zip_path.unlink(missing_ok=True)


# ── Exclude patterns ──────────────────────────────────────────────────────


class TestShouldExclude:
    """Unit tests for the _should_exclude() function."""

    def test_simple_filename_match(self):
        assert _should_exclude("app.log", ["*.log"])

    def test_simple_filename_no_match(self):
        assert not _should_exclude("app.py", ["*.log"])

    def test_nested_path_matches_filename_pattern(self):
        assert _should_exclude("src/debug/trace.log", ["*.log"])

    def test_directory_name_match(self):
        assert _should_exclude("node_modules/express/index.js", ["node_modules"])

    def test_directory_name_no_false_positive(self):
        assert not _should_exclude("my_node_modules/x.js", ["node_modules"])

    def test_pattern_with_slash_matches_full_path(self):
        assert _should_exclude("src/main.py", ["src/*.py"])

    def test_pattern_with_slash_no_deep_match(self):
        assert not _should_exclude("src/utils/helper.py", ["src/*.py"])

    def test_dotfile_exact_match(self):
        assert _should_exclude(".env", [".env"])

    def test_dotfile_no_partial_match(self):
        assert not _should_exclude(".envrc", [".env"])

    def test_multiple_patterns(self):
        assert _should_exclude("debug.log", ["*.pyc", "*.log"])
        assert _should_exclude("cache.pyc", ["*.pyc", "*.log"])
        assert not _should_exclude("main.py", ["*.pyc", "*.log"])

    def test_trailing_slash_stripped(self):
        assert _should_exclude("__pycache__/module.pyc", ["__pycache__/"])

    def test_wildcard_star_matches_all(self):
        assert _should_exclude("anything.txt", ["*"])


class TestExcludePatterns:
    """Integration tests for exclude patterns in create_archive()."""

    def test_single_pattern_excludes_files(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "debug.log").write_text("log data")

        zip_path = create_archive([d], "test", exclude=["*.log"])
        try:
            names = _zip_names(zip_path)
            assert "proj/main.py" in names
            assert "proj/debug.log" not in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_multiple_patterns(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "cache.pyc").write_bytes(b"\x00")
        (d / "debug.log").write_text("log")

        zip_path = create_archive([d], "test", exclude=["*.log", "*.pyc"])
        try:
            names = _zip_names(zip_path)
            assert names == ["proj/main.py"]
        finally:
            zip_path.unlink(missing_ok=True)

    def test_directory_exclusion(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "src").mkdir()
        (d / "src" / "app.py").write_text("app")
        nm = d / "node_modules"
        nm.mkdir()
        (nm / "pkg").mkdir()
        (nm / "pkg" / "index.js").write_text("js")

        zip_path = create_archive([d], "test", exclude=["node_modules"])
        try:
            names = _zip_names(zip_path)
            assert "proj/src/app.py" in names
            assert all("node_modules" not in n for n in names)
        finally:
            zip_path.unlink(missing_ok=True)

    def test_nested_path_exclusion(self, tmp_path: Path):
        d = tmp_path / "proj"
        (d / "src" / "utils").mkdir(parents=True)
        (d / "src" / "main.py").write_text("main")
        (d / "src" / "utils" / "helper.py").write_text("helper")

        zip_path = create_archive([d], "test", exclude=["src/*.py"])
        try:
            names = _zip_names(zip_path)
            # src/*.py only matches src/main.py, not src/utils/helper.py
            assert "proj/src/main.py" not in names
            assert "proj/src/utils/helper.py" in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_no_matches_includes_all(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")

        zip_path = create_archive([d], "test", exclude=["*.xyz"])
        try:
            names = _zip_names(zip_path)
            assert "proj/a.txt" in names
            assert "proj/b.txt" in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_exclude_everything_raises_error(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")

        with pytest.raises(ValueError, match="No files found"):
            create_archive([d], "test", exclude=["*"])

    def test_exclude_top_level_file(self, tmp_path: Path):
        f1 = tmp_path / "keep.txt"
        f1.write_text("keep")
        f2 = tmp_path / "skip.log"
        f2.write_text("skip")

        zip_path = create_archive([f1, f2], "test", exclude=["*.log"])
        try:
            names = _zip_names(zip_path)
            assert "keep.txt" in names
            assert "skip.log" not in names
        finally:
            zip_path.unlink(missing_ok=True)

    def test_empty_exclude_list_no_filtering(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "a.txt").write_text("a")

        zip_path = create_archive([d], "test", exclude=[])
        try:
            names = _zip_names(zip_path)
            assert "proj/a.txt" in names
        finally:
            zip_path.unlink(missing_ok=True)


# ── Password encryption ───────────────────────────────────────────────────


class TestEncryptedArchive:
    def test_encrypted_zip_requires_password(self, tmp_path: Path):
        f = tmp_path / "secret.txt"
        f.write_text("confidential data")

        zip_path = create_archive([f], "enc_test", password="mypassword")
        try:
            # Cannot read without password
            with pyzipper.AESZipFile(zip_path, "r") as zf:
                with pytest.raises(RuntimeError):
                    zf.read("secret.txt")
        finally:
            zip_path.unlink(missing_ok=True)

    def test_encrypted_zip_readable_with_correct_password(self, tmp_path: Path):
        f = tmp_path / "secret.txt"
        f.write_text("confidential data")

        zip_path = create_archive([f], "enc_test", password="mypassword")
        try:
            with pyzipper.AESZipFile(zip_path, "r") as zf:
                zf.setpassword(b"mypassword")
                assert zf.read("secret.txt") == b"confidential data"
        finally:
            zip_path.unlink(missing_ok=True)

    def test_encrypted_zip_with_fast_mode(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("test data")

        zip_path = create_archive([f], "enc_fast", fast=True, password="pass123")
        try:
            with pyzipper.AESZipFile(zip_path, "r") as zf:
                zf.setpassword(b"pass123")
                assert zf.read("data.txt") == b"test data"
        finally:
            zip_path.unlink(missing_ok=True)

    def test_encrypted_zip_directory(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "a.txt").write_text("aaa")
        (d / "b.txt").write_text("bbb")

        zip_path = create_archive([d], "enc_dir", password="dirpass")
        try:
            with pyzipper.AESZipFile(zip_path, "r") as zf:
                zf.setpassword(b"dirpass")
                assert zf.read("proj/a.txt") == b"aaa"
                assert zf.read("proj/b.txt") == b"bbb"
        finally:
            zip_path.unlink(missing_ok=True)

    def test_no_password_creates_standard_zip(self, tmp_path: Path):
        f = tmp_path / "normal.txt"
        f.write_text("normal")

        zip_path = create_archive([f], "no_enc")
        try:
            # Standard zipfile should be able to read it (no encryption)
            with zipfile.ZipFile(zip_path, "r") as zf:
                assert zf.read("normal.txt") == b"normal"
        finally:
            zip_path.unlink(missing_ok=True)

    def test_encrypted_with_progress_callback(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        bytes_reported: list[int] = []
        zip_path = create_archive(
            [f], "enc_cb", password="pass", progress_callback=bytes_reported.append
        )
        try:
            assert len(bytes_reported) >= 1
            assert sum(bytes_reported) == 11  # "hello world" = 11 bytes
        finally:
            zip_path.unlink(missing_ok=True)
