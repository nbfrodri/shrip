"""Base class for upload backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


class UploadBackend(ABC):
    """Abstract base class for upload service backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short name for this backend (e.g., 'gofile')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name (e.g., 'gofile.io')."""

    @property
    @abstractmethod
    def max_size(self) -> Optional[int]:
        """Maximum file size in bytes, or None for unlimited."""

    @property
    @abstractmethod
    def retention(self) -> str:
        """Human-readable retention policy."""

    @abstractmethod
    def upload(
        self,
        file_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        **kwargs: object,
    ) -> "UploadResult":
        """Upload a file and return the result."""


# Re-use UploadResult from upload.py to avoid circular imports
from shrip.upload import UploadResult  # noqa: E402, F401
