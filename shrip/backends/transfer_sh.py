"""transfer.sh upload backend."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

from shrip.backends.base import UploadBackend
from shrip.upload import UploadError, UploadResult

TRANSFER_SH_URL = "https://transfer.sh"
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 3600


class TransferShBackend(UploadBackend):
    """Upload to transfer.sh — no auth, ~10 GB limit, 14-day retention."""

    @property
    def name(self) -> str:
        return "transfer"

    @property
    def display_name(self) -> str:
        return "transfer.sh"

    @property
    def max_size(self) -> Optional[int]:
        return 10 * 1024 * 1024 * 1024  # ~10 GB

    @property
    def retention(self) -> str:
        return "14 days"

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
                    f"{TRANSFER_SH_URL}/{file_path.name}",
                    data=monitor,
                    headers={"Content-Type": monitor.content_type},
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )

            if resp.status_code != 200:
                raise UploadError(f"transfer.sh returned HTTP {resp.status_code}.")

            url = resp.text.strip()
            if not url.startswith("http"):
                raise UploadError("Unexpected response from transfer.sh.")

            return UploadResult(url=url, md5="")

        except requests.exceptions.ConnectionError as e:
            raise UploadError(
                "Could not reach transfer.sh — check your internet connection."
            ) from e
        except requests.exceptions.Timeout as e:
            raise UploadError("Upload to transfer.sh timed out.") from e
        except requests.exceptions.RequestException as e:
            raise UploadError(f"Upload to transfer.sh failed: {e}") from e
