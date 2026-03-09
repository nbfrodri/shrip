"""CLI entry point — Typer app with Rich progress bars."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TransferSpeedColumn,
)

from shrip import __version__
from shrip.archive import create_archive, sanitize_name
from shrip.upload import UploadError, upload_to_gofile

app = typer.Typer(
    name="shrip",
    help="Zip and share files from the terminal.",
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"shrip {__version__}")
        raise typer.Exit()


@app.command()
def main(
    paths: Annotated[
        list[Path],
        typer.Argument(help="Files and/or folders to share."),
    ],
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Archive name (without .zip)."),
    ] = "shrip_archive",
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

    zip_path: Path | None = None
    try:
        # ── Compress ─────────────────────────────────────────────────
        # Count total files for the progress bar
        total_files = 0
        for p in paths:
            rp = p.resolve()
            if rp.is_file():
                total_files += 1
            elif rp.is_dir():
                total_files += sum(1 for f in rp.rglob("*") if f.is_file())
                if total_files == 0:
                    total_files = 1  # empty dir counts as 1 entry

        console.print(
            f"\n[cyan]Compressing {item_count} {item_label} into {safe_name}.zip...[/cyan]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} files"),
            console=console,
        ) as progress:
            task = progress.add_task("Compressing", total=total_files)

            def on_file_compressed(file_path: Path) -> None:
                progress.advance(task)

            zip_path = create_archive(paths, name, progress_callback=on_file_compressed)

        # ── Upload ───────────────────────────────────────────────────
        zip_size = zip_path.stat().st_size
        console.print("[cyan]Uploading to gofile.io...[/cyan]")

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
                progress.update(task, completed=cumulative)

            download_url = upload_to_gofile(zip_path, progress_callback=on_bytes_sent)

        # ── Success ──────────────────────────────────────────────────
        console.print("\n[bold green]Success! Your file is live:[/bold green]")
        console.print(f"[bold]{download_url}[/bold]")
        console.print(
            "\n[dim](Files are automatically deleted after a period of inactivity.)[/dim]\n"
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
