"""CLI entry point — Typer app with Rich progress bars."""

import getpass
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Annotated, List, Optional, Union

import click
import typer
import typer.core
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TransferSpeedColumn,
)

from shrip import __version__
from shrip.backends import DEFAULT_BACKEND, get_backend, list_backends
from shrip.archive import (
    _collect_files,
    _is_incompressible,
    create_archive,
    preview_archive,
    sanitize_name,
)
from shrip.ignore import collect_ignore_patterns
from shrip.upload import UploadError


class _ArgsFirstCommand(typer.core.TyperCommand):
    """Show positional args before [OPTIONS] in the usage line."""

    def format_usage(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        pieces = self.collect_usage_pieces(ctx)
        args = [p for p in pieces if p != "[OPTIONS]"]
        opts = [p for p in pieces if p == "[OPTIONS]"]
        formatter.write_usage(ctx.command_path, " ".join(args + opts))


app = typer.Typer(
    name="shrip",
    help="Zip and share files from the terminal.",
    add_completion=False,
)

_no_color = "NO_COLOR" in os.environ
_is_interactive = sys.stdout.isatty()
console = Console(no_color=_no_color, force_terminal=_is_interactive)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _human_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _copy_to_clipboard(text: str) -> bool:
    """Try to copy text to the system clipboard. Returns True on success."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(
                ["clip"],
                input=text.encode("utf-16le"),
                check=True,
                timeout=5,
            )
            return True
        elif system == "Darwin":
            subprocess.run(
                ["pbcopy"],
                input=text.encode(),
                check=True,
                timeout=5,
            )
            return True
        else:
            # Linux — try xclip, then xsel, then wl-copy (Wayland)
            for cmd in (
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
            ):
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
                    return True
    except (subprocess.SubprocessError, OSError):
        pass
    return False


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _resolve_password(
    interactive: bool,
    password_file: Optional[Path],
    password_env: bool,
    json_mode: bool,
    dry_run: bool,
) -> Optional[str]:
    """Resolve the archive password from the various input methods."""
    sources = sum([interactive, password_file is not None, password_env])
    if sources > 1:
        _error_exit("Cannot combine --password, --password-file, and --password-env.", json_mode)
    if sources == 0:
        return None

    # Dry run doesn't need the actual password
    if dry_run:
        return "__dry_run_placeholder__"

    if password_env:
        pw = os.environ.get("SHRIP_PASSWORD")
        if not pw:
            _error_exit("SHRIP_PASSWORD environment variable is not set.", json_mode)
        return pw

    if password_file is not None:
        if not password_file.exists():
            _error_exit(f"Password file not found: {password_file}", json_mode)
        pw = password_file.read_text(encoding="utf-8").splitlines()
        if not pw or not pw[0].strip():
            _error_exit("Password file is empty.", json_mode)
        return pw[0].strip()

    # Interactive prompt
    if not sys.stdin.isatty():
        _error_exit(
            "Cannot prompt for password in non-interactive mode. "
            "Use --password-file or --password-env.",
            json_mode,
        )
    pw1 = getpass.getpass("Enter password: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        _error_exit("Passwords do not match.", json_mode)
    if not pw1:
        _error_exit("Password cannot be empty.", json_mode)
    return pw1


def _error_exit(msg: str, json_mode: bool = False) -> None:
    """Print an error and exit."""
    if json_mode:
        print(json.dumps({"error": msg}))
    else:
        console.print(f"[red]Error:[/red] {msg}")
    raise typer.Exit(code=1)


_DRY_RUN_MAX_FILES = 50


def _get_compression_method(fp: Path, fast: bool) -> str:
    """Return the compression method label for a file."""
    if fast:
        return "stored"
    return "stored" if _is_incompressible(fp) else "deflate"


def _handle_dry_run(
    paths: List[Path],
    safe_name: str,
    fast: bool,
    exclude_list: List[str],
    json_mode: bool = False,
) -> None:
    """Print a preview of what would be archived, then return."""
    included, excluded = preview_archive(paths, exclude=exclude_list or None)

    # Filter out directory-only entries for display
    file_entries = [(fp, arc) for fp, arc in included if not arc.endswith("/")]
    excluded_files = [(fp, arc) for fp, arc in excluded if not arc.endswith("/")]

    if json_mode:
        total_size = sum(fp.stat().st_size for fp, arc in file_entries)
        exc_size = sum(fp.stat().st_size for fp, arc in excluded_files)
        result = {
            "files": [
                {
                    "path": arc,
                    "size": fp.stat().st_size,
                    "compression": _get_compression_method(fp, fast),
                }
                for fp, arc in file_entries
            ],
            "total_files": len(file_entries),
            "total_size": total_size,
            "excluded_files": len(excluded_files),
            "excluded_size": exc_size,
            "archive_name": f"{safe_name}.zip",
            "mode": "no compression" if fast else "compressed",
        }
        print(json.dumps(result))
        return

    console.print("\n[yellow]Dry run — no files will be uploaded.[/yellow]\n")
    console.print(f"Archive name: [bold]{safe_name}.zip[/bold]")
    if fast:
        console.print("Mode: [bold]no compression[/bold] (--fast)")
    else:
        console.print("Mode: [bold]compressed[/bold] (use --fast to skip compression)")
    console.print()

    if not file_entries:
        console.print("[dim]No files would be archived.[/dim]\n")
        return

    # Print file list
    total_size = 0
    shown = 0
    for fp, arc in file_entries:
        if shown >= _DRY_RUN_MAX_FILES:
            remaining = len(file_entries) - _DRY_RUN_MAX_FILES
            console.print(f"  [dim]... and {remaining} more files[/dim]")
            break
        size = fp.stat().st_size
        total_size += size
        method = _get_compression_method(fp, fast)
        if not fast and _is_incompressible(fp):
            method = "stored (pre-compressed)"
        console.print(f"  {arc:<50s} {_human_size(size):>10s}    {method}")
        shown += 1
    else:
        # No break — all files were shown, compute total from all
        total_size = sum(fp.stat().st_size for fp, arc in file_entries)

    file_label = "file" if len(file_entries) == 1 else "files"
    console.print(
        f"\n[bold]{len(file_entries)} {file_label}, "
        f"{_human_size(total_size)} total[/bold]"
        " (estimated archive size may be smaller after compression)"
    )

    # Show excluded summary
    if excluded_files:
        exc_size = sum(fp.stat().st_size for fp, arc in excluded_files)
        exc_label = "file" if len(excluded_files) == 1 else "files"
        console.print(
            f"[dim]Excluded: {len(excluded_files)} {exc_label} "
            f"({_human_size(exc_size)}) by --exclude patterns[/dim]"
        )

    console.print()


# ── CLI ───────────────────────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"shrip {__version__}")
        raise typer.Exit()


def _list_services_callback(value: bool) -> None:
    if value:
        backends = list_backends()
        for b in backends:
            default_tag = "  (default)" if b.name == DEFAULT_BACKEND else ""
            size_str = "no size limit" if b.max_size is None else _human_size(b.max_size)
            console.print(
                f"  [bold]{b.name:<10s}[/bold] {b.display_name:<15s} "
                f"{size_str:<15s} {b.retention}{default_tag}"
            )
        raise typer.Exit()


@app.command(cls=_ArgsFirstCommand)
def main(
    paths: Annotated[
        List[Path],
        typer.Argument(help="Files and/or folders to share."),
    ],
    name: Annotated[
        str,
        typer.Option("--name", "-n", envvar="SHRIP_NAME", help="Archive name (without .zip)."),
    ] = "shrip_archive",
    open_url: Annotated[
        bool,
        typer.Option("--open", "-o", help="Open the download link in your browser."),
    ] = False,
    copy: Annotated[
        bool,
        typer.Option(
            "--copy", "-c", envvar="SHRIP_COPY", help="Copy the download link to clipboard."
        ),
    ] = False,
    exclude: Annotated[
        Optional[List[str]],
        typer.Option("--exclude", "-e", help="Glob pattern to exclude (repeatable)."),
    ] = None,
    fast: Annotated[
        bool,
        typer.Option(
            "--fast",
            "-f",
            envvar="SHRIP_FAST",
            help="Skip compression (faster for large/pre-compressed files).",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Preview what would be archived without compressing or uploading."
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON (for scripting and CI/CD)."),
    ] = False,
    no_ignore: Annotated[
        bool,
        typer.Option("--no-ignore", help="Skip .shripignore file processing."),
    ] = False,
    password: Annotated[
        bool,
        typer.Option("--password", "-p", help="Encrypt archive with AES-256 (interactive prompt)."),
    ] = False,
    password_file: Annotated[
        Optional[Path],
        typer.Option("--password-file", help="Read encryption password from a file."),
    ] = None,
    password_env: Annotated[
        bool,
        typer.Option(
            "--password-env", help="Read encryption password from SHRIP_PASSWORD env var."
        ),
    ] = False,
    service: Annotated[
        str,
        typer.Option(
            "--service",
            "-s",
            envvar="SHRIP_SERVICE",
            help="Upload service: gofile, transfer, or 0x0.",
        ),
    ] = DEFAULT_BACKEND,
    list_services: Annotated[
        Optional[bool],
        typer.Option(
            "--list-services",
            help="List available upload services and exit.",
            callback=_list_services_callback,
            is_eager=True,
        ),
    ] = None,
    zone: Annotated[
        Optional[str],
        typer.Option(
            "--zone",
            "-z",
            envvar="SHRIP_ZONE",
            help="Upload zone: 'eu' (Europe) or 'na' (North America).",
        ),
    ] = None,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Zip files and folders, upload to gofile.io, and get a download link."""
    json_mode = json_output

    # Validate service
    try:
        backend = get_backend(service)
    except ValueError as e:
        _error_exit(str(e), json_mode)

    # Validate zone
    if zone is not None and zone not in ("eu", "na"):
        if json_mode:
            print(json.dumps({"error": "--zone must be 'eu' or 'na'."}))
        else:
            console.print("[red]Error:[/red] --zone must be 'eu' or 'na'.")
        raise typer.Exit(code=1)

    # ── Resolve password ─────────────────────────────────────────────
    archive_password = _resolve_password(password, password_file, password_env, json_mode, dry_run)

    # Normalize name
    if not name or not name.strip():
        name = "shrip_archive"
    safe_name = sanitize_name(name)

    # Validate all paths upfront, report ALL invalid ones at once
    invalid = [p for p in paths if not p.resolve().exists()]
    if invalid:
        if json_mode:
            msg = "; ".join(f"Path does not exist: {p}" for p in invalid)
            print(json.dumps({"error": msg}))
        else:
            for p in invalid:
                console.print(f"[red]Error:[/red] Path does not exist: {p}")
        raise typer.Exit(code=1)

    # Normalize exclude list (.shripignore + SHRIP_EXCLUDE env var + CLI flags)
    ignore_patterns = collect_ignore_patterns(paths, no_ignore=no_ignore)
    exclude_list = list(ignore_patterns)
    env_exclude = os.environ.get("SHRIP_EXCLUDE", "")
    if env_exclude and not exclude:
        exclude_list.extend(p.strip() for p in env_exclude.split(",") if p.strip())
    if exclude:
        exclude_list.extend(exclude)

    # ── Dry run ─────────────────────────────────────────────────────
    if dry_run:
        _handle_dry_run(paths, safe_name, fast, exclude_list, json_mode=json_mode)
        raise typer.Exit()

    # Count items for display (respecting excludes)
    item_count = len(paths)
    item_label = "item" if item_count == 1 else "items"
    entries = _collect_files(paths, exclude=exclude_list)
    input_size = sum(fp.stat().st_size for fp, arc in entries if not arc.endswith("/"))

    # ── Disk space check ───────────────────────────────────────────
    import tempfile as _tempfile

    try:
        free_space = shutil.disk_usage(_tempfile.gettempdir()).free
        if input_size > free_space:
            if json_mode:
                pass  # warning only — don't pollute JSON output
            else:
                console.print(
                    f"[yellow]Warning:[/yellow] Input is {_human_size(input_size)} but only "
                    f"{_human_size(free_space)} free in temp directory. Compression may fail."
                )
    except OSError:
        pass  # can't check — proceed anyway

    zip_path: Union[Path, None] = None
    try:
        # ── Compress ─────────────────────────────────────────────────
        mode_label = "Packaging" if fast else "Compressing"
        encrypt_note = " (encrypted, AES-256)" if archive_password else ""
        if not json_mode:
            console.print(
                f"\n[cyan]{mode_label} {item_count} {item_label} "
                f"({_human_size(input_size)}) into {safe_name}.zip{encrypt_note}...[/cyan]"
            )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            console=console,
            disable=json_mode,
        ) as progress:
            task = progress.add_task(mode_label, total=input_size)

            def on_file_compressed(bytes_written: int) -> None:
                progress.advance(task, advance=bytes_written)

            zip_path = create_archive(
                paths,
                name,
                fast=fast,
                exclude=exclude_list,
                progress_callback=on_file_compressed,
                password=archive_password,
            )

        # ── Upload ───────────────────────────────────────────────────
        zip_size = zip_path.stat().st_size
        ratio = ((1 - zip_size / input_size) * 100) if input_size > 0 else 0
        service_label = f" to {backend.display_name}" if service != DEFAULT_BACKEND else ""
        if not json_mode:
            if fast:
                console.print(
                    f"[cyan]Packaged to {_human_size(zip_size)}. Uploading{service_label}...[/cyan]"
                )
            else:
                console.print(
                    f"[cyan]Compressed to {_human_size(zip_size)}"
                    f" ({ratio:.0f}% smaller). Uploading{service_label}...[/cyan]"
                )

        # Check file size against backend limit
        if backend.max_size is not None and zip_size > backend.max_size:
            _error_exit(
                f"File is {_human_size(zip_size)} but {backend.display_name} "
                f"has a {_human_size(backend.max_size)} limit. "
                f"Use --service gofile instead.",
                json_mode,
            )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
            disable=json_mode,
        ) as progress:
            task = progress.add_task("Uploading", total=zip_size)

            def on_bytes_sent(cumulative: int) -> None:
                progress.update(task, completed=min(cumulative, zip_size))

            upload_result = backend.upload(zip_path, progress_callback=on_bytes_sent, zone=zone)

        download_url = upload_result.url
        gofile_md5 = upload_result.md5

        # ── Checksums ────────────────────────────────────────────────
        sha256 = _compute_sha256(zip_path)

        # ── Success ──────────────────────────────────────────────────
        clipboard_ok = _copy_to_clipboard(download_url) if copy else False
        clipboard_hint = ""
        if copy and not clipboard_ok:
            system = platform.system()
            if system == "Linux":
                clipboard_hint = "Could not copy to clipboard — install xclip, xsel, or wl-copy."
            else:
                clipboard_hint = "Could not copy to clipboard — check permissions."
        opened = False

        if open_url:
            webbrowser.open(download_url)
            opened = True

        if json_mode:
            file_count = sum(1 for _, arc in entries if not arc.endswith("/"))
            result = {
                "url": download_url,
                "archive": f"{safe_name}.zip",
                "input_size": input_size,
                "archive_size": zip_size,
                "compression_ratio": round(1 - zip_size / input_size, 3) if input_size > 0 else 0,
                "files": file_count,
                "sha256": sha256,
                "encrypted": archive_password is not None,
            }
            if gofile_md5:
                result["md5"] = gofile_md5
            if copy:
                result["copied"] = clipboard_ok
            if open_url:
                result["opened"] = opened
            print(json.dumps(result))
        else:
            # Build panel content with checksums
            panel_lines = [f"[bold]{download_url}[/bold]"]
            panel_lines.append("")
            panel_lines.append(f"[dim]SHA256: {sha256}[/dim]")
            if gofile_md5:
                panel_lines.append(f"[dim]MD5:    {gofile_md5}  (gofile)[/dim]")

            status_parts = ["[bold green]Link copied![/bold green]"] if clipboard_ok else []
            if opened:
                status_parts.append("[bold green]Opened in browser.[/bold green]")

            subtitle = "  ".join(status_parts) if status_parts else None

            console.print()
            console.print(
                Panel(
                    "\n".join(panel_lines),
                    title="[bold green]Ready to share[/bold green]",
                    subtitle=subtitle,
                    border_style="green",
                    padding=(1, 2),
                )
            )
            if clipboard_hint:
                console.print(f"[dim]{clipboard_hint}[/dim]")
            console.print(
                "[dim](Files are automatically deleted after a period of inactivity.)[/dim]\n"
            )

    except KeyboardInterrupt:
        if json_mode:
            print(json.dumps({"error": "Interrupted"}))
        else:
            console.print("\n[yellow]Interrupted.[/yellow]")
        raise typer.Exit(code=130)
    except UploadError as e:
        if json_mode:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        if json_mode:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    finally:
        if zip_path is not None:
            zip_path.unlink(missing_ok=True)
