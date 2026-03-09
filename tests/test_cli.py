"""Tests for shrip.cli module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from shrip.cli import app, _human_size
from shrip.upload import UploadError, UploadResult
from shrip.backends.gofile import GofileBackend

runner = CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_upload(
    return_url: str = "https://gofile.io/d/TestXyz",
    md5: str = "a1b2c3d4e5f67890abcdef1234567890",
):
    """Return a patch that mocks the backend upload to return an UploadResult."""
    result = UploadResult(url=return_url, md5=md5)
    mock_backend = MagicMock(spec=GofileBackend)
    mock_backend.upload.return_value = result
    mock_backend.name = "gofile"
    mock_backend.display_name = "gofile.io"
    mock_backend.max_size = None
    mock_backend.retention = "~10 days inactive"
    return patch("shrip.cli.get_backend", return_value=mock_backend)


def _mock_archive(tmp_path: Path):
    """Return a patch that mocks create_archive to create a real temp zip."""
    fake_zip = tmp_path / ".shrip_test_mock.zip"
    fake_zip.write_bytes(b"PK fake zip content for testing")

    return patch("shrip.cli.create_archive", return_value=fake_zip)


# ── Version flag ─────────────────────────────────────────────────────────────


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "shrip" in result.output

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "shrip" in result.output


# ── No arguments ─────────────────────────────────────────────────────────────


class TestNoArgs:
    def test_no_paths_shows_error(self):
        result = runner.invoke(app, [])
        assert result.exit_code != 0


# ── Invalid paths ────────────────────────────────────────────────────────────


class TestInvalidPaths:
    def test_single_nonexistent_path(self):
        result = runner.invoke(app, ["/nonexistent/path/file.txt"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_multiple_invalid_paths_all_reported(self):
        result = runner.invoke(app, ["/fake/one.txt", "/fake/two.txt"])
        assert result.exit_code == 1
        assert "one.txt" in result.output
        assert "two.txt" in result.output

    def test_mix_of_valid_and_invalid(self, tmp_path: Path):
        good = tmp_path / "good.txt"
        good.write_text("hello")
        result = runner.invoke(app, [str(good), "/fake/bad.txt"])
        assert result.exit_code == 1
        assert "bad.txt" in result.output


# ── Successful run ───────────────────────────────────────────────────────────


class TestSuccessfulRun:
    def test_basic_file_upload(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        with _mock_archive(tmp_path) as mock_arc, _mock_upload() as mock_upl:
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "https://gofile.io/d/TestXyz" in result.output
        assert "Ready to share" in result.output
        mock_arc.assert_called_once()
        mock_upl.assert_called_once()

    def test_directory_upload(self, tmp_path: Path):
        d = tmp_path / "mydir"
        d.mkdir()
        (d / "file.txt").write_text("content")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(d)])

        assert result.exit_code == 0
        assert "Ready to share" in result.output

    def test_multiple_inputs(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f1.write_text("a")
        f2 = tmp_path / "b.txt"
        f2.write_text("b")
        d = tmp_path / "folder"
        d.mkdir()
        (d / "c.txt").write_text("c")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f1), str(f2), str(d)])

        assert result.exit_code == 0
        assert "3 items" in result.output


# ── --name flag ──────────────────────────────────────────────────────────────


class TestNameFlag:
    def test_custom_name(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path) as mock_arc, _mock_upload():
            result = runner.invoke(app, [str(f), "--name", "my-release"])

        assert result.exit_code == 0
        assert "my-release.zip" in result.output
        # Verify name was passed to create_archive
        call_args = mock_arc.call_args
        assert call_args[0][1] == "my-release" or call_args.kwargs.get("name") == "my-release"

    def test_short_name_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "-n", "release-v2"])

        assert result.exit_code == 0
        assert "release-v2.zip" in result.output

    def test_name_with_zip_suffix(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "-n", "test.zip"])

        assert result.exit_code == 0
        # Should show "test.zip" not "test.zip.zip"
        assert "test.zip.zip" not in result.output
        assert "test.zip" in result.output

    def test_empty_name_uses_default(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "-n", ""])

        assert result.exit_code == 0
        assert "shrip_archive.zip" in result.output


# ── Upload errors ────────────────────────────────────────────────────────────


class TestUploadErrors:
    def test_upload_error_shown(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        mock_backend = MagicMock(spec=GofileBackend)
        mock_backend.upload.side_effect = UploadError("Could not reach gofile.io")
        mock_backend.name = "gofile"
        mock_backend.display_name = "gofile.io"
        mock_backend.max_size = None

        with (
            _mock_archive(tmp_path),
            patch("shrip.cli.get_backend", return_value=mock_backend),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 1
        assert "Could not reach gofile.io" in result.output

    def test_archive_error_shown(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with patch(
            "shrip.cli.create_archive",
            side_effect=ValueError("No files found to archive."),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 1
        assert "No files found" in result.output


# ── Temp file cleanup ────────────────────────────────────────────────────────


class TestCleanup:
    def test_zip_deleted_after_success(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        fake_zip = tmp_path / ".shrip_cleanup_test.zip"
        fake_zip.write_bytes(b"PK fake")

        with patch("shrip.cli.create_archive", return_value=fake_zip), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert not fake_zip.exists(), "Temp zip should be deleted after success"

    def test_zip_deleted_after_upload_error(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        fake_zip = tmp_path / ".shrip_cleanup_error.zip"
        fake_zip.write_bytes(b"PK fake")

        mock_backend = MagicMock(spec=GofileBackend)
        mock_backend.upload.side_effect = UploadError("Network failure")
        mock_backend.name = "gofile"
        mock_backend.display_name = "gofile.io"
        mock_backend.max_size = None

        with (
            patch("shrip.cli.create_archive", return_value=fake_zip),
            patch("shrip.cli.get_backend", return_value=mock_backend),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 1
        assert not fake_zip.exists(), "Temp zip should be deleted after upload error"

    def test_zip_deleted_after_keyboard_interrupt(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        fake_zip = tmp_path / ".shrip_cleanup_interrupt.zip"
        fake_zip.write_bytes(b"PK fake")

        mock_backend = MagicMock(spec=GofileBackend)
        mock_backend.upload.side_effect = KeyboardInterrupt
        mock_backend.name = "gofile"
        mock_backend.display_name = "gofile.io"
        mock_backend.max_size = None

        with (
            patch("shrip.cli.create_archive", return_value=fake_zip),
            patch("shrip.cli.get_backend", return_value=mock_backend),
        ):
            runner.invoke(app, [str(f)])

        assert not fake_zip.exists(), "Temp zip should be deleted after Ctrl+C"


# ── --copy flag ─────────────────────────────────────────────────────────────


class TestCopyFlag:
    def test_copy_flag_calls_clipboard(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=True) as mock_clip,
        ):
            result = runner.invoke(app, [str(f), "--copy"])

        assert result.exit_code == 0
        mock_clip.assert_called_once_with("https://gofile.io/d/TestXyz")
        assert "copied" in result.output.lower()

    def test_copy_short_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=True),
        ):
            result = runner.invoke(app, [str(f), "-c"])

        assert result.exit_code == 0

    def test_copy_not_called_without_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard") as mock_clip,
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        mock_clip.assert_not_called()


# ── --open flag ─────────────────────────────────────────────────────────────


class TestOpenFlag:
    def test_open_flag_calls_webbrowser(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli.webbrowser.open") as mock_open,
        ):
            result = runner.invoke(app, [str(f), "--open"])

        assert result.exit_code == 0
        mock_open.assert_called_once_with("https://gofile.io/d/TestXyz")

    def test_open_not_called_without_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli.webbrowser.open") as mock_open,
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        mock_open.assert_not_called()


# ── Compression info ────────────────────────────────────────────────────────


class TestCompressionInfo:
    def test_shows_input_size(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("a" * 1000)

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        # Should show something like "1000 B" or "1.0 KB"
        assert "Compressing 1 item" in result.output

    def test_shows_compressed_size(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "Compressed to" in result.output
        assert "smaller" in result.output


# ── _human_size helper ──────────────────────────────────────────────────────


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500) == "500 B"

    def test_kilobytes(self):
        assert _human_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert _human_size(2 * 1024 * 1024) == "2.0 MB"

    def test_gigabytes(self):
        assert _human_size(3 * 1024**3) == "3.0 GB"

    def test_zero(self):
        assert _human_size(0) == "0 B"


# ── --dry-run flag ─────────────────────────────────────────────────────────


class TestDryRun:
    def test_basic_dry_run(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        result = runner.invoke(app, [str(f), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "hello.txt" in result.output
        assert "1 file" in result.output

    def test_dry_run_no_upload(self, tmp_path: Path):
        """Verify no upload or archive creation happens."""
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            patch("shrip.cli.create_archive") as mock_arc,
            _mock_upload() as mock_get,
        ):
            result = runner.invoke(app, [str(f), "--dry-run"])

        assert result.exit_code == 0
        mock_arc.assert_not_called()
        mock_get.return_value.upload.assert_not_called()

    def test_dry_run_with_exclude(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "debug.log").write_text("log data")

        result = runner.invoke(app, [str(d), "--dry-run", "--exclude", "*.log"])
        assert result.exit_code == 0
        assert "main.py" in result.output
        assert "debug.log" not in result.output or "Excluded" in result.output

    def test_dry_run_shows_excluded_summary(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "debug.log").write_text("log data here")

        result = runner.invoke(app, [str(d), "--dry-run", "--exclude", "*.log"])
        assert result.exit_code == 0
        assert "Excluded" in result.output
        assert "1 file" in result.output

    def test_dry_run_with_fast(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--dry-run", "--fast"])
        assert result.exit_code == 0
        assert "no compression" in result.output
        assert "stored" in result.output

    def test_dry_run_with_name(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--dry-run", "--name", "my-release"])
        assert result.exit_code == 0
        assert "my-release.zip" in result.output

    def test_dry_run_no_temp_files(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        import tempfile

        before = set(Path(tempfile.gettempdir()).glob(".shrip_*"))
        result = runner.invoke(app, [str(f), "--dry-run"])
        after = set(Path(tempfile.gettempdir()).glob(".shrip_*"))

        assert result.exit_code == 0
        assert after == before, "No temp files should be created during dry run"

    def test_dry_run_invalid_path(self):
        result = runner.invoke(app, ["/nonexistent/path.txt", "--dry-run"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_dry_run_directory(self, tmp_path: Path):
        d = tmp_path / "mydir"
        d.mkdir()
        (d / "a.txt").write_text("aaaa")
        (d / "b.txt").write_text("bb")

        result = runner.invoke(app, [str(d), "--dry-run"])
        assert result.exit_code == 0
        assert "mydir/a.txt" in result.output
        assert "mydir/b.txt" in result.output
        assert "2 files" in result.output

    def test_dry_run_shows_compression_method(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "code.py").write_text("print('hi')")
        (d / "image.jpg").write_bytes(b"\xff\xd8" * 50)

        result = runner.invoke(app, [str(d), "--dry-run"])
        assert result.exit_code == 0
        assert "deflate" in result.output
        assert "stored" in result.output


# ── --json flag ────────────────────────────────────────────────────────────


class TestJsonOutput:
    def test_json_success(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["url"] == "https://gofile.io/d/TestXyz"
        assert data["archive"] == "shrip_archive.zip"
        assert "input_size" in data
        assert "archive_size" in data
        assert "compression_ratio" in data
        assert data["files"] == 1

    def test_json_no_rich_markup(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("hello")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "--json"])

        assert result.exit_code == 0
        # No Rich markup should appear
        assert "[bold" not in result.output
        assert "[cyan" not in result.output
        assert "[green" not in result.output

    def test_json_error_invalid_path(self):
        result = runner.invoke(app, ["/nonexistent/file.txt", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output.strip())
        assert "error" in data
        assert "does not exist" in data["error"]

    def test_json_upload_error(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        mock_backend = MagicMock(spec=GofileBackend)
        mock_backend.upload.side_effect = UploadError("Connection failed")
        mock_backend.name = "gofile"
        mock_backend.display_name = "gofile.io"
        mock_backend.max_size = None

        with (
            _mock_archive(tmp_path),
            patch("shrip.cli.get_backend", return_value=mock_backend),
        ):
            result = runner.invoke(app, [str(f), "--json"])

        assert result.exit_code == 1
        data = json.loads(result.output.strip())
        assert data["error"] == "Connection failed"

    def test_json_dry_run(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("print('hi')")

        result = runner.invoke(app, [str(d), "--json", "--dry-run"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["total_files"] == 1
        assert len(data["files"]) == 1
        assert data["files"][0]["path"] == "proj/main.py"
        assert data["archive_name"] == "shrip_archive.zip"
        assert data["mode"] == "compressed"

    def test_json_dry_run_with_exclude(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "debug.log").write_text("log data here")

        result = runner.invoke(
            app, [str(d), "--json", "--dry-run", "--exclude", "*.log"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["total_files"] == 1
        assert data["excluded_files"] == 1
        assert data["excluded_size"] > 0

    def test_json_dry_run_fast_mode(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--json", "--dry-run", "--fast"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["mode"] == "no compression"
        assert data["files"][0]["compression"] == "stored"

    def test_json_with_copy_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=True),
        ):
            result = runner.invoke(app, [str(f), "--json", "--copy"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["copied"] is True

    def test_json_with_custom_name(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "--json", "--name", "my-release"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["archive"] == "my-release.zip"

    def test_json_zone_error(self):
        result = runner.invoke(app, ["file.txt", "--json", "--zone", "invalid"])
        assert result.exit_code == 1
        data = json.loads(result.output.strip())
        assert "error" in data

    def test_json_includes_checksums(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert "sha256" in data
        assert len(data["sha256"]) == 64  # hex SHA256
        assert "md5" in data


# ── Checksum display ──────────────────────────────────────────────────────


class TestChecksumDisplay:
    def test_sha256_shown_in_panel(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "SHA256:" in result.output

    def test_md5_shown_in_panel(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        with _mock_archive(tmp_path), _mock_upload(md5="abc123def456"):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "MD5:" in result.output
        assert "abc123def456" in result.output

    def test_md5_hidden_when_empty(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        with _mock_archive(tmp_path), _mock_upload(md5=""):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "SHA256:" in result.output
        assert "MD5:" not in result.output


# ── CI/CD Integration (Phase 5) ──────────────────────────────────────────


class TestEnvironmentVariables:
    def test_shrip_zone_env(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload() as mock_get_backend:
            result = runner.invoke(app, [str(f)], env={"SHRIP_ZONE": "eu"})

        assert result.exit_code == 0
        # Zone should have been passed to backend.upload as kwarg
        mock_backend = mock_get_backend.return_value
        call_kwargs = mock_backend.upload.call_args
        assert call_kwargs.kwargs.get("zone") == "eu"

    def test_cli_flag_overrides_env(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload() as mock_get_backend:
            result = runner.invoke(
                app, [str(f), "--zone", "na"], env={"SHRIP_ZONE": "eu"}
            )

        assert result.exit_code == 0
        mock_backend = mock_get_backend.return_value
        call_kwargs = mock_backend.upload.call_args
        assert call_kwargs.kwargs.get("zone") == "na"

    def test_shrip_name_env(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)], env={"SHRIP_NAME": "env-archive"})

        assert result.exit_code == 0
        assert "env-archive.zip" in result.output

    def test_shrip_fast_env(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path) as mock_arc, _mock_upload():
            result = runner.invoke(app, [str(f)], env={"SHRIP_FAST": "1"})

        assert result.exit_code == 0
        assert "Packaging" in result.output

    def test_shrip_exclude_env(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "debug.log").write_text("log data")

        result = runner.invoke(
            app, [str(d), "--dry-run"], env={"SHRIP_EXCLUDE": "*.log"}
        )
        assert result.exit_code == 0
        assert "main.py" in result.output
        # Either debug.log is excluded or shown in excluded summary
        assert "Excluded" in result.output or "debug.log" not in result.output

    def test_shrip_exclude_env_comma_separated(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "main.py").write_text("code")
        (d / "debug.log").write_text("log")
        (d / "cache.pyc").write_bytes(b"\x00")

        result = runner.invoke(
            app, [str(d), "--dry-run"], env={"SHRIP_EXCLUDE": "*.log,*.pyc"}
        )
        assert result.exit_code == 0
        assert "main.py" in result.output


class TestExitCodes:
    def test_success_exit_0(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0

    def test_invalid_path_exit_1(self):
        result = runner.invoke(app, ["/nonexistent/file.txt"])
        assert result.exit_code == 1

    def test_upload_error_exit_1(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        mock_backend = MagicMock(spec=GofileBackend)
        mock_backend.upload.side_effect = UploadError("fail")
        mock_backend.name = "gofile"
        mock_backend.display_name = "gofile.io"
        mock_backend.max_size = None

        with (
            _mock_archive(tmp_path),
            patch("shrip.cli.get_backend", return_value=mock_backend),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 1

    def test_dry_run_exit_0(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--dry-run"])
        assert result.exit_code == 0

    def test_invalid_zone_exit_1(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--zone", "invalid"])
        assert result.exit_code == 1


# ── Password flags ────────────────────────────────────────────────────────


class TestPasswordFlags:
    def test_password_env_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(
                app, [str(f), "--password-env"],
                env={"SHRIP_PASSWORD": "secret123"},
            )

        assert result.exit_code == 0

    def test_password_env_missing(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--password-env"])
        assert result.exit_code == 1
        assert "SHRIP_PASSWORD" in result.output

    def test_password_file_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")
        pw_file = tmp_path / "keyfile"
        pw_file.write_text("my-secret-password\n")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(
                app, [str(f), "--password-file", str(pw_file)]
            )

        assert result.exit_code == 0

    def test_password_file_not_found(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(
            app, [str(f), "--password-file", "/nonexistent/keyfile"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_password_file_empty(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")
        pw_file = tmp_path / "empty_keyfile"
        pw_file.write_text("")

        result = runner.invoke(
            app, [str(f), "--password-file", str(pw_file)]
        )
        assert result.exit_code == 1
        assert "empty" in result.output

    def test_mutual_exclusion(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")
        pw_file = tmp_path / "keyfile"
        pw_file.write_text("pass\n")

        result = runner.invoke(
            app, [str(f), "--password", "--password-file", str(pw_file)]
        )
        assert result.exit_code == 1
        assert "Cannot combine" in result.output

    def test_json_shows_encrypted_field(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(
                app, [str(f), "--json", "--password-env"],
                env={"SHRIP_PASSWORD": "secret"},
            )

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["encrypted"] is True

    def test_shows_encrypted_in_compress_message(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(
                app, [str(f), "--password-env"],
                env={"SHRIP_PASSWORD": "secret"},
            )

        assert result.exit_code == 0
        assert "encrypted" in result.output.lower() or "AES-256" in result.output


# ── Backend / Service selection ───────────────────────────────────────────


class TestServiceFlag:
    def test_list_services(self):
        result = runner.invoke(app, ["--list-services"])
        assert result.exit_code == 0
        assert "gofile" in result.output
        assert "transfer" in result.output
        assert "0x0" in result.output

    def test_invalid_service(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        result = runner.invoke(app, [str(f), "--service", "unknown"])
        assert result.exit_code == 1
        assert "Unknown service" in result.output

    def test_default_service_is_gofile(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload() as mock_get:
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        mock_get.assert_called_once_with("gofile")

    def test_explicit_service_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload() as mock_get:
            result = runner.invoke(app, [str(f), "--service", "gofile"])

        assert result.exit_code == 0
        mock_get.assert_called_once_with("gofile")


# ── Phase 9: UX Polish ──────────────────────────────────────────────────


class TestClipboardHint:
    def test_clipboard_failure_shows_hint_linux(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=False),
            patch("shrip.cli.platform.system", return_value="Linux"),
        ):
            result = runner.invoke(app, [str(f), "--copy"])

        assert result.exit_code == 0
        assert "Could not copy to clipboard" in result.output
        assert "xclip" in result.output

    def test_clipboard_failure_shows_hint_windows(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=False),
            patch("shrip.cli.platform.system", return_value="Windows"),
        ):
            result = runner.invoke(app, [str(f), "--copy"])

        assert result.exit_code == 0
        assert "Could not copy to clipboard" in result.output
        assert "permissions" in result.output

    def test_clipboard_success_no_hint(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=True),
        ):
            result = runner.invoke(app, [str(f), "--copy"])

        assert result.exit_code == 0
        assert "Could not copy" not in result.output

    def test_no_copy_flag_no_hint(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "Could not copy" not in result.output

    def test_clipboard_failure_json_mode(self, tmp_path: Path):
        """JSON mode should show copied: false, no hint text."""
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli._copy_to_clipboard", return_value=False),
        ):
            result = runner.invoke(app, [str(f), "--json", "--copy"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["copied"] is False
        assert "Could not copy" not in result.output


class TestDiskSpaceWarning:
    def test_low_disk_space_warning(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("a" * 1000)

        fake_usage = MagicMock()
        fake_usage.free = 500  # less than input size

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli.shutil.disk_usage", return_value=fake_usage),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "free in temp directory" in result.output

    def test_sufficient_space_no_warning(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        fake_usage = MagicMock()
        fake_usage.free = 10 * 1024 * 1024 * 1024  # 10 GB

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli.shutil.disk_usage", return_value=fake_usage),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "Warning" not in result.output

    def test_disk_check_error_ignored(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli.shutil.disk_usage", side_effect=OSError("no access")),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "Ready to share" in result.output

    def test_disk_space_warning_not_in_json(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("a" * 1000)

        fake_usage = MagicMock()
        fake_usage.free = 500

        with (
            _mock_archive(tmp_path),
            _mock_upload(),
            patch("shrip.cli.shutil.disk_usage", return_value=fake_usage),
        ):
            result = runner.invoke(app, [str(f), "--json"])

        assert result.exit_code == 0
        # JSON output should be valid JSON without warning text mixed in
        data = json.loads(result.output.strip())
        assert "url" in data


class TestFastModeMessage:
    def test_fast_mode_shows_packaged(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f), "--fast"])

        assert result.exit_code == 0
        assert "Packaged to" in result.output
        assert "smaller" not in result.output

    def test_normal_mode_shows_compressed(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload():
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        assert "Compressed to" in result.output
        assert "smaller" in result.output
