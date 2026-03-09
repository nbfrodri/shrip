"""0x0.st upload backend."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

from shrip.backends.base import UploadBackend
from shrip.upload import UploadError, UploadResult

ZERO_X0_URL = "https://0x0.st"
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 3600
MAX_SIZE = 512 * 1024 * 1024  # 512 MB


class ZeroX0Backend(UploadBackend):
    """Upload to 0x0.st — no auth, 512 MB limit, 30 days–1 year retention."""

    @property
    def name(self) -> str:
        return "0x0"

    @property
    def display_name(self) -> str:
        return "0x0.st"

    @property
    def max_size(self) -> Optional[int]:
        return MAX_SIZE

    @property
    def retention(self) -> str:
        return "30 days to 1 year"

    def upload(
        self,
        file_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        **kwargs: object,
    ) -> UploadResult:
        file_path = file_path.resolve()
        file_size = file_path.stat().st_size

        if file_size == 0:
            raise ValueError("Archive is empty, nothing to upload.")

        if file_size > MAX_SIZE:
            from shrip.cli import _human_size

            raise UploadError(
                f"File is {_human_size(file_size)} but 0x0.st has a "
                f"{_human_size(MAX_SIZE)} limit. Use --service gofile instead."
            )

        try:
            with open(file_path, "rb") as f:
                encoder = MultipartEncoder(
                    fields={"file": (file_path.name, f, "application/octet-stream")}
                )

                if progress_callback is not None:
                    last_update = [0.0]

                    def _throttled(monitor: MultipartEncoderMonitor) -> None:
                        now = time.monotonic()
                        if now - last_update[0] >= 0.1 or monitor.bytes_read >= monitor.len:
                            progress_callback(monitor.bytes_read)
                            last_update[0] = now

                    monitor = MultipartEncoderMonitor(encoder, _throttled)
                else:
                    monitor = MultipartEncoderMonitor(encoder)

                resp = requests.post(
                    ZERO_X0_URL,
                    data=monitor,
                    headers={"Content-Type": monitor.content_type},
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )

            if resp.status_code != 200:
                raise UploadError(f"0x0.st returned HTTP {resp.status_code}.")

            url = resp.text.strip()
            if not url.startswith("http"):
                raise UploadError("Unexpected response from 0x0.st.")

            return UploadResult(url=url, md5="")

        except requests.exceptions.ConnectionError as e:
            raise UploadError("Could not reach 0x0.st — check your internet connection.") from e
        except requests.exceptions.Timeout as e:
            raise UploadError("Upload to 0x0.st timed out.") from e
        except requests.exceptions.RequestException as e:
            raise UploadError(f"Upload to 0x0.st failed: {e}") from e
