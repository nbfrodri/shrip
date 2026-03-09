"""Tests for shrip.cli module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from shrip.cli import app, _human_size
from shrip.upload import UploadError

runner = CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_upload(return_url: str = "https://gofile.io/d/TestXyz"):
    """Return a patch that mocks upload_to_gofile to return a URL."""
    return patch("shrip.cli.upload_to_gofile", return_value=return_url)


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

        with _mock_archive(tmp_path) as mock_arc, _mock_upload():
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

        with _mock_archive(tmp_path), patch(
            "shrip.cli.upload_to_gofile",
            side_effect=UploadError("Could not reach gofile.io"),
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

        with patch("shrip.cli.create_archive", return_value=fake_zip), patch(
            "shrip.cli.upload_to_gofile",
            side_effect=UploadError("Network failure"),
        ):
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 1
        assert not fake_zip.exists(), "Temp zip should be deleted after upload error"

    def test_zip_deleted_after_keyboard_interrupt(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        fake_zip = tmp_path / ".shrip_cleanup_interrupt.zip"
        fake_zip.write_bytes(b"PK fake")

        with patch("shrip.cli.create_archive", return_value=fake_zip), patch(
            "shrip.cli.upload_to_gofile",
            side_effect=KeyboardInterrupt,
        ):
            result = runner.invoke(app, [str(f)])

        assert not fake_zip.exists(), "Temp zip should be deleted after Ctrl+C"


# ── --copy flag ─────────────────────────────────────────────────────────────


class TestCopyFlag:
    def test_copy_flag_calls_clipboard(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload(), patch(
            "shrip.cli._copy_to_clipboard", return_value=True
        ) as mock_clip:
            result = runner.invoke(app, [str(f), "--copy"])

        assert result.exit_code == 0
        mock_clip.assert_called_once_with("https://gofile.io/d/TestXyz")
        assert "copied" in result.output.lower()

    def test_copy_short_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload(), patch(
            "shrip.cli._copy_to_clipboard", return_value=True
        ):
            result = runner.invoke(app, [str(f), "-c"])

        assert result.exit_code == 0

    def test_copy_not_called_without_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload(), patch(
            "shrip.cli._copy_to_clipboard"
        ) as mock_clip:
            result = runner.invoke(app, [str(f)])

        assert result.exit_code == 0
        mock_clip.assert_not_called()


# ── --open flag ─────────────────────────────────────────────────────────────


class TestOpenFlag:
    def test_open_flag_calls_webbrowser(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload(), patch(
            "shrip.cli.webbrowser.open"
        ) as mock_open:
            result = runner.invoke(app, [str(f), "--open"])

        assert result.exit_code == 0
        mock_open.assert_called_once_with("https://gofile.io/d/TestXyz")

    def test_open_not_called_without_flag(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_text("data")

        with _mock_archive(tmp_path), _mock_upload(), patch(
            "shrip.cli.webbrowser.open"
        ) as mock_open:
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
