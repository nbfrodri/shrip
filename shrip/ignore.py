"""Parse .shripignore and .gitignore files for exclude patterns."""

from __future__ import annotations

from pathlib import Path

IGNORE_FILES = (".shripignore", ".gitignore")


def parse_ignore_file(path: Path) -> list[str]:
    """
    Read and parse an ignore file (.shripignore or .gitignore).

    Returns a list of glob patterns. Comments (#), empty lines, and
    trailing whitespace are stripped. Negation (!) patterns are preserved
    as-is for upstream handling.
    """
    patterns: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)

    return patterns


def collect_ignore_patterns(
    paths: list[Path],
    no_ignore: bool = False,
) -> list[str]:
    """
    Collect patterns from .shripignore and .gitignore files found in
    input directories and the current working directory.

    .shripignore takes priority (loaded first). .gitignore patterns are
    merged in. Duplicate patterns are skipped.

    Args:
        paths: Input paths provided by the user.
        no_ignore: If True, skip all ignore file processing entirely.

    Returns:
        Combined list of patterns from all found ignore files.
    """
    if no_ignore:
        return []

    seen_files: set[Path] = set()
    seen_patterns: set[str] = set()
    patterns: list[str] = []

    def _add_patterns(file_path: Path) -> None:
        resolved = file_path.resolve()
        if resolved in seen_files:
            return
        if not file_path.is_file():
            return
        seen_files.add(resolved)
        for pat in parse_ignore_file(file_path):
            if pat not in seen_patterns:
                seen_patterns.add(pat)
                patterns.append(pat)

    # Check CWD (.shripignore first, then .gitignore)
    for name in IGNORE_FILES:
        _add_patterns(Path.cwd() / name)

    # Check each input directory root
    for p in paths:
        p = p.resolve()
        directory = p if p.is_dir() else p.parent

        for name in IGNORE_FILES:
            _add_patterns(directory / name)

    return patterns
