"""Archive creation module — zips files and directories into a temp file."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional


def sanitize_name(name: str) -> str:
    """Strip dangerous characters and normalize an archive name."""
    name = name.removesuffix(".zip")
    name = re.sub(r'[/\\:*?"<>|]', "", name)
    name = name.replace(" ", "_")
    name = name.strip("._")
    return name or "shrip_archive"


def _resolve_safe(path: Path, allowed_roots: list[Path]) -> Path | None:
    """Resolve a path and return it only if it lives under one of the allowed roots."""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None


def _collect_files(paths: list[Path]) -> list[tuple[Path, str]]:
    """
    Walk all input paths and return a list of (absolute_path, arcname) pairs.

    - Files are stored with their filename only.
    - Directories are walked recursively; files inside are stored relative to the
      directory itself (e.g., mydir/sub/file.txt → mydir/sub/file.txt).
    - Duplicate arcnames are made unique by prefixing with a counter.
    """
    entries: list[tuple[Path, str]] = []
    seen_arcnames: dict[str, int] = {}
    allowed_roots = [p.resolve().parent if p.is_file() else p.resolve() for p in paths]

    for input_path in paths:
        input_path = input_path.resolve()

        if input_path.is_file():
            arcname = input_path.name
            arcname = _deduplicate_arcname(arcname, seen_arcnames)
            entries.append((input_path, arcname))

        elif input_path.is_dir():
            dir_name = input_path.name
            has_children = False
            for child in sorted(input_path.rglob("*")):
                if not child.is_file():
                    continue
                # Symlink safety: resolve and verify target is inside allowed roots
                if child.is_symlink():
                    safe = _resolve_safe(child, allowed_roots)
                    if safe is None:
                        continue
                relative = child.relative_to(input_path)
                arcname = str(Path(dir_name) / relative)
                arcname = _deduplicate_arcname(arcname, seen_arcnames)
                entries.append((child, arcname))
                has_children = True

            # Empty directory: add a directory entry
            if not has_children:
                entries.append((input_path, dir_name + "/"))

    return entries


def _deduplicate_arcname(arcname: str, seen: dict[str, int]) -> str:
    """If arcname was already used, prefix with a counter to make it unique."""
    if arcname not in seen:
        seen[arcname] = 1
        return arcname
    seen[arcname] += 1
    stem = Path(arcname)
    new_name = f"{stem.parent}/{stem.stem}_{seen[arcname]}{stem.suffix}" if str(stem.parent) != "." else f"{stem.stem}_{seen[arcname]}{stem.suffix}"
    # Recurse in case the new name also collides
    return _deduplicate_arcname(new_name, seen)


def create_archive(
    paths: list[Path],
    name: str = "shrip_archive",
    progress_callback: Optional[Callable[[Path], None]] = None,
) -> Path:
    """
    Create a temporary .zip archive containing all provided files and directories.

    Args:
        paths: Files and/or directories to include.
        name: Archive base name (without .zip). Sanitized automatically.
        progress_callback: Called with each file path after it is added to the archive.

    Returns:
        Path to the created temporary zip file.

    Raises:
        FileNotFoundError: If any input path does not exist.
        PermissionError: If any input file cannot be read.
        ValueError: If no files are found to archive.
    """
    safe_name = sanitize_name(name)

    # Validate all paths exist and are readable upfront
    for p in paths:
        resolved = p.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        if resolved.is_file() and not _is_readable(resolved):
            raise PermissionError(f"Cannot read file: {p}")

    entries = _collect_files(paths)

    # Check we have something to zip (allow empty dirs, but not zero entries)
    if not entries:
        raise ValueError("No files found to archive.")

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".zip", prefix=f".shrip_{safe_name}_"
    )
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path, arcname in entries:
                if arcname.endswith("/"):
                    # Empty directory entry
                    zf.mkdir(arcname)
                else:
                    zf.write(file_path, arcname)
                if progress_callback is not None:
                    progress_callback(file_path)
        return tmp_path
    except Exception:
        # Cleanup on failure
        tmp_path.unlink(missing_ok=True)
        raise


def _is_readable(path: Path) -> bool:
    """Check if a file can be opened for reading."""
    try:
        with open(path, "rb"):
            return True
    except (PermissionError, OSError):
        return False
