"""Upload backend registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shrip.backends.gofile import GofileBackend
from shrip.backends.transfer_sh import TransferShBackend
from shrip.backends.zero_x0 import ZeroX0Backend

if TYPE_CHECKING:
    from shrip.backends.base import UploadBackend

BACKENDS: dict[str, type[UploadBackend]] = {
    "gofile": GofileBackend,
    "transfer": TransferShBackend,
    "0x0": ZeroX0Backend,
}

DEFAULT_BACKEND = "gofile"


def get_backend(name: str) -> UploadBackend:
    """Get a backend instance by name."""
    if name not in BACKENDS:
        available = ", ".join(BACKENDS)
        raise ValueError(f"Unknown service: {name}. Available: {available}")
    return BACKENDS[name]()


def list_backends() -> list[UploadBackend]:
    """Return instances of all available backends."""
    return [cls() for cls in BACKENDS.values()]
