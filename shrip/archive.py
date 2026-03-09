"""Archive creation module — zips files and directories into a temp file."""

from __future__ import annotations

import fnmatch
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

import pyzipper


def sanitize_name(name: str) -> str:
    """Strip dangerous characters and normalize an archive name."""
    name = name.removesuffix(".zip")
    name = re.sub(r'[/\\:*?"<>|]', "", name)
    name = name.replace(" ", "_")
    name = name.strip("._")
    return name or "shrip_archive"


def _to_posix(path_str: str) -> str:
    """Normalize a path string to forward slashes (ZIP spec requirement)."""
    return path_str.replace("\\", "/")


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


def _should_exclude(relative_path: str, exclude_patterns: list[str]) -> bool:
    """Check if a relative path matches any exclude pattern."""
    # relative_path is always posix-style (forward slashes)
    # Strip trailing / for directory patterns
    parts = relative_path.rstrip("/").split("/")
    for pattern in exclude_patterns:
        clean_pattern = pattern.rstrip("/")
        if "/" not in clean_pattern:
            # Pattern without / → match against any path component
            for part in parts:
                if fnmatch.fnmatch(part, clean_pattern):
                    return True
        else:
            # Pattern with / → match component-by-component so * doesn't cross /
            pat_parts = clean_pattern.split("/")
            path_parts = relative_path.rstrip("/").split("/")
            pat_depth = len(pat_parts)
            if pat_depth <= len(path_parts):
                if all(fnmatch.fnmatch(path_parts[i], pat_parts[i]) for i in range(pat_depth)):
                    return True
    return False


def _collect_files(
    paths: list[Path],
    exclude: list[str] | None = None,
) -> list[tuple[Path, str]]:
    """
    Walk all input paths and return a list of (absolute_path, arcname) pairs.

    - Files are stored with their filename only.
    - Directories are walked recursively; files inside are stored relative to the
      directory itself (e.g., mydir/sub/file.txt → mydir/sub/file.txt).
    - Duplicate arcnames are made unique by prefixing with a counter.
    - All arcnames use forward slashes per the ZIP specification.
    - Files matching any exclude pattern are skipped.
    """
    exclude_patterns = exclude or []
    entries: list[tuple[Path, str]] = []
    seen_arcnames: dict[str, int] = {}
    allowed_roots = [p.resolve().parent if p.is_file() else p.resolve() for p in paths]

    for input_path in paths:
        input_path = input_path.resolve()

        if input_path.is_file():
            arcname = input_path.name
            if _should_exclude(arcname, exclude_patterns):
                continue
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
                relative_posix = _to_posix(str(relative))
                arcname = _to_posix(f"{dir_name}/{relative}")
                if _should_exclude(relative_posix, exclude_patterns):
                    continue
                arcname = _deduplicate_arcname(arcname, seen_arcnames)
                entries.append((child, arcname))
                has_children = True

            # Empty directory: add a directory entry (only if nothing was excluded)
            if not has_children:
                entries.append((input_path, dir_name + "/"))

    return entries


def _deduplicate_arcname(arcname: str, seen: dict[str, int]) -> str:
    """If arcname was already used, prefix with a counter to make it unique."""
    if arcname not in seen:
        seen[arcname] = 1
        return arcname
    seen[arcname] += 1
    # Use PurePosixPath to keep forward slashes on all platforms
    stem = PurePosixPath(arcname)
    new_name = (
        f"{stem.parent}/{stem.stem}_{seen[arcname]}{stem.suffix}"
        if str(stem.parent) != "."
        else f"{stem.stem}_{seen[arcname]}{stem.suffix}"
    )
    # Recurse in case the new name also collides
    return _deduplicate_arcname(new_name, seen)


_CHUNK_SIZE = 1024 * 1024  # 1 MiB chunks for progress reporting

# File extensions that are already compressed — DEFLATE wastes CPU on these
_INCOMPRESSIBLE_EXTENSIONS = frozenset(
    {
        # Archives
        ".zip",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".zst",
        ".lz4",
        ".lzma",
        ".cab",
        ".tar.gz",
        # Disk images
        ".iso",
        ".img",
        ".dmg",
        ".vhd",
        ".vhdx",
        ".vmdk",
        ".qcow2",
        # Video
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".ts",
        # Audio
        ".mp3",
        ".aac",
        ".ogg",
        ".opus",
        ".flac",
        ".wma",
        ".m4a",
        # Images
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".avif",
        ".heic",
        ".heif",
        # Documents (already compressed internally)
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".epub",
        # Executables / packages
        ".deb",
        ".rpm",
        ".apk",
        ".appimage",
        ".snap",
        ".msi",
        ".exe",
        # Other
        ".whl",
        ".jar",
        ".war",
        ".egg",
    }
)


def _is_incompressible(file_path: Path) -> bool:
    """Check if a file is likely already compressed based on its extension."""
    return file_path.suffix.lower() in _INCOMPRESSIBLE_EXTENSIONS


def create_archive(
    paths: list[Path],
    name: str = "shrip_archive",
    fast: bool = False,
    exclude: list[str] | None = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    password: Optional[str] = None,
) -> Path:
    """
    Create a temporary .zip archive containing all provided files and directories.

    Args:
        paths: Files and/or directories to include.
        name: Archive base name (without .zip). Sanitized automatically.
        fast: If True, skip compression entirely (ZIP_STORED). If False,
              auto-detect: use ZIP_STORED for already-compressed formats,
              ZIP_DEFLATED for the rest.
        exclude: Glob patterns for files/directories to skip.
        progress_callback: Called with the number of bytes just compressed.
        password: If set, encrypt the archive with AES-256 using this password.

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

    entries = _collect_files(paths, exclude=exclude)

    # Check we have something to zip
    if not entries:
        raise ValueError("No files found to archive.")
    # If exclude patterns were used and only empty dir stubs remain, that's an error
    has_files = any(not arc.endswith("/") for _, arc in entries)
    if exclude and not has_files:
        raise ValueError("No files found to archive.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix=f".shrip_{safe_name}_")
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        if password:
            _create_encrypted_archive(tmp_path, entries, fast, progress_callback, password)
        else:
            _create_standard_archive(tmp_path, entries, fast, progress_callback)
        return tmp_path
    except Exception:
        # Cleanup on failure
        tmp_path.unlink(missing_ok=True)
        raise


def _create_standard_archive(
    tmp_path: Path,
    entries: list[tuple[Path, str]],
    fast: bool,
    progress_callback: Optional[Callable[[int], None]],
) -> None:
    """Create a standard (unencrypted) zip archive."""
    with zipfile.ZipFile(tmp_path, "w") as zf:
        for file_path, arcname in entries:
            if arcname.endswith("/"):
                zf.writestr(zipfile.ZipInfo(arcname), "")
            else:
                _write_file_chunked(zf, file_path, arcname, fast, progress_callback)


def _create_encrypted_archive(
    tmp_path: Path,
    entries: list[tuple[Path, str]],
    fast: bool,
    progress_callback: Optional[Callable[[int], None]],
    password: str,
) -> None:
    """Create an AES-256 encrypted zip archive using pyzipper."""
    with pyzipper.AESZipFile(
        tmp_path,
        "w",
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(password.encode("utf-8"))
        for file_path, arcname in entries:
            if arcname.endswith("/"):
                zf.writestr(pyzipper.ZipInfo(arcname), "")
            else:
                _write_file_chunked_encrypted(zf, file_path, arcname, fast, progress_callback)


def _write_file_chunked(
    zf: zipfile.ZipFile,
    file_path: Path,
    arcname: str,
    fast: bool,
    progress_callback: Optional[Callable[[int], None]],
) -> None:
    """Write a file into the zip archive in chunks, reporting progress."""
    zinfo = zipfile.ZipInfo.from_file(file_path, arcname)
    if fast or _is_incompressible(file_path):
        zinfo.compress_type = zipfile.ZIP_STORED
    else:
        zinfo.compress_type = zipfile.ZIP_DEFLATED
    with zf.open(zinfo, "w") as dest, open(file_path, "rb") as src:
        while True:
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            dest.write(chunk)
            if progress_callback is not None:
                progress_callback(len(chunk))


def _write_file_chunked_encrypted(
    zf: pyzipper.AESZipFile,
    file_path: Path,
    arcname: str,
    fast: bool,
    progress_callback: Optional[Callable[[int], None]],
) -> None:
    """Write a file into an encrypted zip archive, reporting progress."""
    compress_type = (
        pyzipper.ZIP_STORED if (fast or _is_incompressible(file_path)) else pyzipper.ZIP_DEFLATED
    )
    # pyzipper doesn't support chunked writing via zf.open(); read then writestr
    data = bytearray()
    with open(file_path, "rb") as src:
        while True:
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            data.extend(chunk)
            if progress_callback is not None:
                progress_callback(len(chunk))
    zf.writestr(arcname, bytes(data), compress_type=compress_type)


def preview_archive(
    paths: list[Path],
    exclude: list[str] | None = None,
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    """
    Preview what would be archived without creating the zip.

    Returns:
        (included, excluded) — each a list of (absolute_path, arcname) pairs.

    Raises:
        FileNotFoundError: If any input path does not exist.
        PermissionError: If any input file cannot be read.
    """
    for p in paths:
        resolved = p.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        if resolved.is_file() and not _is_readable(resolved):
            raise PermissionError(f"Cannot read file: {p}")

    all_entries = _collect_files(paths, exclude=None)
    if exclude:
        included = _collect_files(paths, exclude=exclude)
        included_arcnames = {arc for _, arc in included}
        excluded = [(fp, arc) for fp, arc in all_entries if arc not in included_arcnames]
    else:
        included = all_entries
        excluded = []

    return included, excluded


def _is_readable(path: Path) -> bool:
    """Check if a file can be opened for reading."""
    try:
        with open(path, "rb"):
            return True
    except (PermissionError, OSError):
        return False
