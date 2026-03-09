"""Tests for shrip.upload module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests

from shrip.upload import UploadError, upload_to_gofile


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_response(status_code: int = 200, json_data: dict | None = None, bad_json: bool = False):
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    if bad_json:
        resp.json.side_effect = ValueError("No JSON")
    else:
        resp.json.return_value = json_data or {}
    return resp


def _success_json(url: str = "https://gofile.io/d/AbCd123") -> dict:
    return {
        "status": "ok",
        "data": {
            "downloadPage": url,
            "code": "AbCd123",
            "fileName": "test.zip",
            "md5": "abc123",
            "guestToken": "token123",
        },
    }


# ── Success cases ────────────────────────────────────────────────────────────


class TestUploadSuccess:
    def test_returns_download_url(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"fake zip content")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, _success_json())
            url = upload_to_gofile(f)

        assert url == "https://gofile.io/d/AbCd123"

    def test_sends_correct_request(self, tmp_path: Path):
        f = tmp_path / "archive.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, _success_json())
            upload_to_gofile(f)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["timeout"] == (10, 300)
        # files arg should contain a tuple with the filename
        files_arg = call_kwargs.kwargs["files"]
        assert "file" in files_arg
        assert files_arg["file"][0] == "archive.zip"

    def test_progress_callback_is_called(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"x" * 100)

        callback_values: list[int] = []

        def fake_post(url, files, timeout):
            """Simulate requests.post by reading the file object, triggering the progress wrapper."""
            file_tuple = files["file"]
            reader = file_tuple[1]
            # Read all content like requests would
            while True:
                chunk = reader.read(32)
                if not chunk:
                    break
            return _mock_response(200, _success_json())

        with patch("shrip.upload.requests.post", side_effect=fake_post):
            upload_to_gofile(f, progress_callback=callback_values.append)

        # Callback should have been called at least once
        assert len(callback_values) > 0
        # Final value should equal file size
        assert callback_values[-1] == 100


# ── Empty file ───────────────────────────────────────────────────────────────


class TestEmptyFile:
    def test_rejects_zero_byte_file(self, tmp_path: Path):
        f = tmp_path / "empty.zip"
        f.write_bytes(b"")

        with pytest.raises(ValueError, match="empty"):
            upload_to_gofile(f)


# ── Network errors ───────────────────────────────────────────────────────────


class TestNetworkErrors:
    def test_connection_error(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError()
            with pytest.raises(UploadError, match="Could not reach gofile.io"):
                upload_to_gofile(f)

    def test_timeout(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout()
            with pytest.raises(UploadError, match="timed out"):
                upload_to_gofile(f)

    def test_ssl_error(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.SSLError()
            with pytest.raises(UploadError, match="SSL"):
                upload_to_gofile(f)

    def test_generic_request_exception(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.RequestException("something broke")
            with pytest.raises(UploadError, match="something broke"):
                upload_to_gofile(f)


# ── HTTP status errors ───────────────────────────────────────────────────────


class TestHTTPErrors:
    def test_rate_limited_429(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(429)
            with pytest.raises(UploadError, match="Rate limited"):
                upload_to_gofile(f)

    def test_server_error_500(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(500)
            with pytest.raises(UploadError, match="temporarily unavailable"):
                upload_to_gofile(f)

    def test_server_error_503(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(503)
            with pytest.raises(UploadError, match="temporarily unavailable"):
                upload_to_gofile(f)

    def test_unexpected_status_code(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(403)
            with pytest.raises(UploadError, match="HTTP 403"):
                upload_to_gofile(f)


# ── Malformed responses ──────────────────────────────────────────────────────


class TestMalformedResponses:
    def test_invalid_json(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, bad_json=True)
            with pytest.raises(UploadError, match="Invalid response"):
                upload_to_gofile(f)

    def test_status_not_ok(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "error", "data": {"message": "file too large"}}
        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, body)
            with pytest.raises(UploadError, match="file too large"):
                upload_to_gofile(f)

    def test_status_not_ok_no_message(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "error"}
        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, body)
            with pytest.raises(UploadError, match="error"):
                upload_to_gofile(f)

    def test_missing_data_field(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "ok"}
        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, body)
            with pytest.raises(UploadError, match="API may have changed"):
                upload_to_gofile(f)

    def test_data_is_not_dict(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "ok", "data": "unexpected string"}
        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, body)
            with pytest.raises(UploadError, match="API may have changed"):
                upload_to_gofile(f)

    def test_missing_download_page(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "ok", "data": {"code": "abc", "fileName": "test.zip"}}
        with patch("shrip.upload.requests.post") as mock_post:
            mock_post.return_value = _mock_response(200, body)
            with pytest.raises(UploadError, match="API may have changed"):
                upload_to_gofile(f)
