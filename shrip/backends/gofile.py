"""Gofile.io upload backend."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from shrip.backends.base import UploadBackend
from shrip.upload import UploadResult, upload_to_gofile


class GofileBackend(UploadBackend):
    """Upload to gofile.io — no auth, no size limit."""

    @property
    def name(self) -> str:
        return "gofile"

    @property
    def display_name(self) -> str:
        return "gofile.io"

    @property
    def max_size(self) -> Optional[int]:
        return None  # Unlimited

    @property
    def retention(self) -> str:
        return "~10 days inactive"

    def upload(
        self,
        file_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        **kwargs: object,
    ) -> UploadResult:
        zone = kwargs.get("zone")
        return upload_to_gofile(
            file_path,
            zone=str(zone) if zone else None,
            progress_callback=progress_callback,
        )
