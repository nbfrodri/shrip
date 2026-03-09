"""Tests for shrip.upload module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from shrip.upload import UploadError, upload_to_gofile

_MOCK_SESSION = "shrip.upload._create_session"


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


def _mock_session(post_return=None, post_side_effect=None):
    """Create a mock session whose .post() is controlled."""
    session = MagicMock()
    if post_side_effect is not None:
        session.post.side_effect = post_side_effect
    elif post_return is not None:
        session.post.return_value = post_return
    return session


# ── Success cases ────────────────────────────────────────────────────────────


class TestUploadSuccess:
    def test_returns_download_url(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"fake zip content")

        session = _mock_session(post_return=_mock_response(200, _success_json()))
        with patch(_MOCK_SESSION, return_value=session):
            url = upload_to_gofile(f)

        assert url == "https://gofile.io/d/AbCd123"

    def test_sends_correct_request(self, tmp_path: Path):
        f = tmp_path / "archive.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_return=_mock_response(200, _success_json()))
        with patch(_MOCK_SESSION, return_value=session):
            upload_to_gofile(f)

        session.post.assert_called_once()
        call_kwargs = session.post.call_args
        assert call_kwargs.kwargs["timeout"] == (30, 3600)
        # Streaming upload uses data= with MultipartEncoderMonitor
        assert "data" in call_kwargs.kwargs
        assert "Content-Type" in call_kwargs.kwargs["headers"]
        assert "multipart/form-data" in call_kwargs.kwargs["headers"]["Content-Type"]

    def test_progress_callback_is_called(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"x" * 100)

        callback_values: list[int] = []

        def fake_post(url, data, headers, timeout):
            """Simulate session.post by reading the encoder to trigger progress."""
            while True:
                chunk = data.read(32)
                if not chunk:
                    break
            return _mock_response(200, _success_json())

        session = _mock_session(post_side_effect=fake_post)
        with patch(_MOCK_SESSION, return_value=session):
            upload_to_gofile(f, progress_callback=callback_values.append)

        # Callback should have been called at least once
        assert len(callback_values) > 0
        # Final value should be >= file size (includes multipart boundary overhead)
        assert callback_values[-1] >= 100


# ── Empty file ───────────────────────────────────────────────────────────────


class TestEmptyFile:
    def test_rejects_zero_byte_file(self, tmp_path: Path):
        f = tmp_path / "empty.zip"
        f.write_bytes(b"")

        with pytest.raises(ValueError, match="empty"):
            upload_to_gofile(f)


# ── Network errors ───────────────────────────────────────────────────────────


class TestNetworkErrors:
    @patch("shrip.upload.RETRY_BACKOFF", 0)
    def test_connection_error(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_side_effect=requests.exceptions.ConnectionError())
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="Could not reach gofile.io"):
                upload_to_gofile(f)

    @patch("shrip.upload.RETRY_BACKOFF", 0)
    def test_timeout(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_side_effect=requests.exceptions.Timeout())
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="timed out"):
                upload_to_gofile(f)

    def test_ssl_error(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_side_effect=requests.exceptions.SSLError())
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="SSL"):
                upload_to_gofile(f)

    def test_generic_request_exception(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(
            post_side_effect=requests.exceptions.RequestException("something broke")
        )
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="something broke"):
                upload_to_gofile(f)


# ── Retry logic ──────────────────────────────────────────────────────────────


class TestRetryLogic:
    @patch("shrip.upload.RETRY_BACKOFF", 0)
    def test_retries_on_connection_error_then_succeeds(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(
            post_side_effect=[
                requests.exceptions.ConnectionError(),
                _mock_response(200, _success_json()),
            ]
        )
        with patch(_MOCK_SESSION, return_value=session):
            url = upload_to_gofile(f)

        assert url == "https://gofile.io/d/AbCd123"
        assert session.post.call_count == 2

    @patch("shrip.upload.RETRY_BACKOFF", 0)
    def test_retries_on_timeout_then_succeeds(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(
            post_side_effect=[
                requests.exceptions.Timeout(),
                _mock_response(200, _success_json()),
            ]
        )
        with patch(_MOCK_SESSION, return_value=session):
            url = upload_to_gofile(f)

        assert url == "https://gofile.io/d/AbCd123"
        assert session.post.call_count == 2

    @patch("shrip.upload.RETRY_BACKOFF", 0)
    def test_exhausts_retries(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_side_effect=requests.exceptions.ConnectionError())
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="Could not reach gofile.io"):
                upload_to_gofile(f)

        assert session.post.call_count == 3  # MAX_RETRIES


# ── HTTP status errors ───────────────────────────────────────────────────────


class TestHTTPErrors:
    def test_rate_limited_429(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_return=_mock_response(429))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="Rate limited"):
                upload_to_gofile(f)

    def test_server_error_500(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_return=_mock_response(500))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="temporarily unavailable"):
                upload_to_gofile(f)

    def test_server_error_503(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_return=_mock_response(503))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="temporarily unavailable"):
                upload_to_gofile(f)

    def test_unexpected_status_code(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_return=_mock_response(403))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="HTTP 403"):
                upload_to_gofile(f)


# ── Malformed responses ──────────────────────────────────────────────────────


class TestMalformedResponses:
    def test_invalid_json(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        session = _mock_session(post_return=_mock_response(200, bad_json=True))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="Invalid response"):
                upload_to_gofile(f)

    def test_status_not_ok(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "error", "data": {"message": "file too large"}}
        session = _mock_session(post_return=_mock_response(200, body))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="file too large"):
                upload_to_gofile(f)

    def test_status_not_ok_no_message(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "error"}
        session = _mock_session(post_return=_mock_response(200, body))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="error"):
                upload_to_gofile(f)

    def test_missing_data_field(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "ok"}
        session = _mock_session(post_return=_mock_response(200, body))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="API may have changed"):
                upload_to_gofile(f)

    def test_data_is_not_dict(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "ok", "data": "unexpected string"}
        session = _mock_session(post_return=_mock_response(200, body))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="API may have changed"):
                upload_to_gofile(f)

    def test_missing_download_page(self, tmp_path: Path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")

        body = {"status": "ok", "data": {"code": "abc", "fileName": "test.zip"}}
        session = _mock_session(post_return=_mock_response(200, body))
        with patch(_MOCK_SESSION, return_value=session):
            with pytest.raises(UploadError, match="API may have changed"):
                upload_to_gofile(f)
