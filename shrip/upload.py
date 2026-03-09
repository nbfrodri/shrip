"""Upload module — sends a file to gofile.io and returns the download URL."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import requests

GOFILE_UPLOAD_URL = "https://upload.gofile.io/uploadfile"
CONNECT_TIMEOUT = 10  # seconds
READ_TIMEOUT = 300  # seconds (5 min, generous for large files)


class UploadError(Exception):
    """Raised when the upload fails for any reason."""


class _ProgressReader:
    """Wraps a file object to track bytes read and call a progress callback."""

    def __init__(self, fileobj, total_size: int, callback: Callable[[int], None]):
        self._fileobj = fileobj
        self._total_size = total_size
        self._bytes_read = 0
        self._callback = callback

    def read(self, size: int = -1) -> bytes:
        chunk = self._fileobj.read(size)
        self._bytes_read += len(chunk)
        self._callback(self._bytes_read)
        return chunk

    def __len__(self) -> int:
        return self._total_size


def upload_to_gofile(
    file_path: Path,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> str:
    """
    Upload a file to gofile.io and return the download page URL.

    Args:
        file_path: Path to the file to upload.
        progress_callback: Called with cumulative bytes sent after each chunk.

    Returns:
        The download page URL (e.g., "https://gofile.io/d/AbCd123").

    Raises:
        UploadError: On any upload or API failure.
        ValueError: If the file is empty (0 bytes).
    """
    file_path = file_path.resolve()
    file_size = file_path.stat().st_size

    if file_size == 0:
        raise ValueError("Archive is empty, nothing to upload.")

    try:
        with open(file_path, "rb") as f:
            if progress_callback is not None:
                reader = _ProgressReader(f, file_size, progress_callback)
                files = {"file": (file_path.name, reader)}
            else:
                files = {"file": (file_path.name, f)}

            response = requests.post(
                GOFILE_UPLOAD_URL,
                files=files,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )

    except requests.exceptions.SSLError as e:
        raise UploadError("SSL verification failed when connecting to gofile.io.") from e
    except requests.exceptions.Timeout as e:
        raise UploadError("Upload timed out — check your connection and try again.") from e
    except requests.exceptions.ConnectionError as e:
        raise UploadError("Could not reach gofile.io — check your internet connection.") from e
    except requests.exceptions.RequestException as e:
        raise UploadError(f"Upload failed: {e}") from e

    if response.status_code == 429:
        raise UploadError("Rate limited by gofile.io — wait a moment and try again.")
    if response.status_code >= 500:
        raise UploadError("gofile.io is temporarily unavailable — try again later.")
    if response.status_code != 200:
        raise UploadError(f"Upload failed with HTTP {response.status_code}.")

    try:
        body = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as e:
        raise UploadError("Invalid response from gofile.io.") from e

    status = body.get("status")
    if status != "ok":
        msg = (
            body.get("data", {}).get("message", "unknown error")
            if isinstance(body.get("data"), dict)
            else status
        )
        raise UploadError(f"gofile.io returned an error: {msg}")

    data = body.get("data")
    if not isinstance(data, dict):
        raise UploadError("Unexpected response from gofile.io — the API may have changed.")

    download_url = data.get("downloadPage")
    if not download_url:
        raise UploadError("Unexpected response from gofile.io — the API may have changed.")

    return download_url
