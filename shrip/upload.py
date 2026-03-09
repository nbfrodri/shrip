"""Upload module — sends a file to gofile.io and returns the download URL."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests
from requests.adapters import HTTPAdapter
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

GOFILE_UPLOAD_URL = "https://upload.gofile.io/uploadfile"
GOFILE_SERVERS_URL = "https://api.gofile.io/servers"
CONNECT_TIMEOUT = 30  # seconds
READ_TIMEOUT = 3600  # seconds (1 hour, supports multi-GB uploads)
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds between retries
UPLOAD_BLOCKSIZE = 1024 * 1024  # 1 MiB — default is 8 KB, way too small for large files


class UploadError(Exception):
    """Raised when the upload fails for any reason."""


@dataclass
class UploadResult:
    """Result of a successful upload to gofile.io."""

    url: str
    md5: str  # MD5 hash returned by gofile.io (may be empty if not provided)


class _LargeBlockAdapter(HTTPAdapter):
    """HTTPAdapter that uses 1 MiB send blocks instead of the default 8 KB."""

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["blocksize"] = UPLOAD_BLOCKSIZE
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def _create_session() -> requests.Session:
    """Create a requests Session with optimized settings for large uploads."""
    session = requests.Session()
    session.mount("https://", _LargeBlockAdapter())
    return session


def _get_server_for_zone(zone: str) -> Optional[str]:
    """Query gofile.io for the best server in the given zone ('eu' or 'na')."""
    try:
        resp = requests.get(
            GOFILE_SERVERS_URL,
            params={"zone": zone},
            timeout=(CONNECT_TIMEOUT, 30),
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                servers = data.get("data", {}).get("servers", [])
                if servers:
                    return servers[0].get("name")
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None


def _get_upload_url(zone: Optional[str]) -> str:
    """Return the upload URL, optionally targeting a specific zone."""
    if zone is not None:
        server = _get_server_for_zone(zone)
        if server:
            return f"https://{server}.gofile.io/contents/uploadfile"
    return GOFILE_UPLOAD_URL


def upload_to_gofile(
    file_path: Path,
    zone: Optional[str] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> UploadResult:
    """
    Upload a file to gofile.io and return the upload result.

    Uses streaming multipart upload to avoid loading the entire file into memory.

    Args:
        file_path: Path to the file to upload.
        zone: Optional upload zone ('eu' or 'na') for server selection.
        progress_callback: Called with cumulative bytes sent after each chunk.

    Returns:
        UploadResult with download URL and MD5 hash.

    Raises:
        UploadError: On any upload or API failure.
        ValueError: If the file is empty (0 bytes).
    """
    file_path = file_path.resolve()
    file_size = file_path.stat().st_size

    if file_size == 0:
        raise ValueError("Archive is empty, nothing to upload.")

    upload_url = _get_upload_url(zone)
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _do_upload(file_path, file_size, upload_url, progress_callback)
            return _parse_response(response)
        except UploadError:
            raise
        except requests.exceptions.SSLError as e:
            raise UploadError("SSL verification failed when connecting to gofile.io.") from e
        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt == MAX_RETRIES:
                raise UploadError("Upload timed out — check your connection and try again.") from e
        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt == MAX_RETRIES:
                raise UploadError(
                    "Could not reach gofile.io — check your internet connection."
                ) from e
        except requests.exceptions.RequestException as e:
            raise UploadError(f"Upload failed: {e}") from e

        # Retry after backoff
        time.sleep(RETRY_BACKOFF * attempt)

    # Should never reach here, but just in case
    raise UploadError(f"Upload failed after {MAX_RETRIES} attempts: {last_error}")


def _do_upload(
    file_path: Path,
    file_size: int,
    upload_url: str,
    progress_callback: Optional[Callable[[int], None]],
) -> requests.Response:
    """Perform a single streaming upload attempt."""
    with open(file_path, "rb") as f:
        encoder = MultipartEncoder(fields={"file": (file_path.name, f, "application/octet-stream")})

        if progress_callback is not None:
            # Throttle callback to ~10 updates/sec to avoid overhead on large files
            last_update = [0.0]

            def _throttled_callback(monitor: MultipartEncoderMonitor) -> None:
                now = time.monotonic()
                if now - last_update[0] >= 0.1 or monitor.bytes_read >= monitor.len:
                    progress_callback(monitor.bytes_read)
                    last_update[0] = now

            monitor = MultipartEncoderMonitor(encoder, _throttled_callback)
        else:
            monitor = MultipartEncoderMonitor(encoder)

        session = _create_session()

        return session.post(
            upload_url,
            data=monitor,
            headers={"Content-Type": monitor.content_type},
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )


def _parse_response(response: requests.Response) -> UploadResult:
    """Parse and validate the gofile.io API response."""
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

    md5 = data.get("md5", "")

    return UploadResult(url=download_url, md5=md5)
