"""CLI entry point — Typer app with Rich progress bars."""

import platform
import shutil
import subprocess
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
from shrip.archive import create_archive, sanitize_name
from shrip.upload import UploadError, upload_to_gofile


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
console = Console()


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


def _total_input_size(paths: List[Path]) -> int:
    """Sum the size of all input files (recursing into directories)."""
    total = 0
    for p in paths:
        rp = p.resolve()
        if rp.is_file():
            total += rp.stat().st_size
        elif rp.is_dir():
            for f in rp.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
    return total


# ── CLI ───────────────────────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"shrip {__version__}")
        raise typer.Exit()


@app.command(cls=_ArgsFirstCommand)
def main(
    paths: Annotated[
        List[Path],
        typer.Argument(help="Files and/or folders to share."),
    ],
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Archive name (without .zip)."),
    ] = "shrip_archive",
    open_url: Annotated[
        bool,
        typer.Option("--open", "-o", help="Open the download link in your browser."),
    ] = False,
    copy: Annotated[
        bool,
        typer.Option("--copy", "-c", help="Copy the download link to clipboard."),
    ] = False,
    fast: Annotated[
        bool,
        typer.Option("--fast", "-f", help="Skip compression (faster for large/pre-compressed files)."),
    ] = False,
    zone: Annotated[
        Optional[str],
        typer.Option("--zone", "-z", help="Upload zone: 'eu' (Europe) or 'na' (North America)."),
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
    # Validate zone
    if zone is not None and zone not in ("eu", "na"):
        console.print("[red]Error:[/red] --zone must be 'eu' or 'na'.")
        raise typer.Exit(code=1)

    # Normalize name
    if not name or not name.strip():
        name = "shrip_archive"
    safe_name = sanitize_name(name)

    # Validate all paths upfront, report ALL invalid ones at once
    invalid = [p for p in paths if not p.resolve().exists()]
    if invalid:
        for p in invalid:
            console.print(f"[red]Error:[/red] Path does not exist: {p}")
        raise typer.Exit(code=1)

    # Count items for display
    item_count = len(paths)
    item_label = "item" if item_count == 1 else "items"
    input_size = _total_input_size(paths)

    zip_path: Union[Path, None] = None
    try:
        # ── Compress ─────────────────────────────────────────────────
        total_files = 0
        for p in paths:
            rp = p.resolve()
            if rp.is_file():
                total_files += 1
            elif rp.is_dir():
                dir_files = sum(1 for f in rp.rglob("*") if f.is_file())
                if dir_files == 0:
                    total_files += 1
                else:
                    total_files += dir_files

        mode_label = "Packaging" if fast else "Compressing"
        console.print(
            f"\n[cyan]{mode_label} {item_count} {item_label} "
            f"({_human_size(input_size)}) into {safe_name}.zip...[/cyan]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(mode_label, total=input_size)

            def on_file_compressed(bytes_written: int) -> None:
                progress.advance(task, advance=bytes_written)

            zip_path = create_archive(
                paths, name, fast=fast, progress_callback=on_file_compressed
            )

        # ── Upload ───────────────────────────────────────────────────
        zip_size = zip_path.stat().st_size
        ratio = ((1 - zip_size / input_size) * 100) if input_size > 0 else 0
        console.print(
            f"[cyan]Compressed to {_human_size(zip_size)}"
            f" ({ratio:.0f}% smaller). Uploading...[/cyan]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Uploading", total=zip_size)

            def on_bytes_sent(cumulative: int) -> None:
                progress.update(task, completed=min(cumulative, zip_size))

            download_url = upload_to_gofile(
                zip_path, zone=zone, progress_callback=on_bytes_sent
            )

        # ── Success ──────────────────────────────────────────────────
        clipboard_ok = _copy_to_clipboard(download_url) if copy else False

        status_parts = ["[bold green]Link copied![/bold green]"] if clipboard_ok else []
        if open_url:
            webbrowser.open(download_url)
            status_parts.append("[bold green]Opened in browser.[/bold green]")

        subtitle = "  ".join(status_parts) if status_parts else None

        console.print()
        console.print(
            Panel(
                f"[bold]{download_url}[/bold]",
                title="[bold green]Ready to share[/bold green]",
                subtitle=subtitle,
                border_style="green",
                padding=(1, 2),
            )
        )
        console.print(
            "[dim](Files are automatically deleted after a period of inactivity.)[/dim]\n"
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        raise typer.Exit(code=130)
    except UploadError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        console.print(f"\n[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
    finally:
        if zip_path is not None:
            zip_path.unlink(missing_ok=True)
