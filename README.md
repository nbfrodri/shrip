# shrip

**Zip and share files from the terminal — no browser needed.**

`shrip` bundles files and folders into a compressed archive and uploads it to [gofile.io](https://gofile.io), giving you a temporary public download link instantly. No accounts, no configuration, no context-switching.

## Installation

**With [pipx](https://pipx.pypa.io/) (recommended):**

```bash
pipx install shrip
```

> pipx installs `shrip` in an isolated environment and adds it to your PATH automatically. Install pipx with `pip install pipx` or see the [pipx docs](https://pipx.pypa.io/stable/installation/).

**With pip:**

```bash
pip install shrip
```

> On Linux/macOS you may need `pip install --user shrip` if not using a virtual environment. Make sure `~/.local/bin` is on your PATH.

**From GitHub:**

```bash
pip install git+https://github.com/nbfrodri/shrip.git
```

> Requires Python 3.9 or higher. Works on Windows, macOS, and Linux.

## Uninstalling

```bash
# If installed with pipx
pipx uninstall shrip

# If installed with pip
pip uninstall shrip
```

## Usage

```bash
# Share a single file
shrip report.pdf

# Share multiple files and folders
shrip ./src/ README.md logo.png --name project-handover

# Custom archive name
shrip ./build/ -n release-v2

# Copy the link to clipboard
shrip file.txt --copy

# Open in browser after upload
shrip file.txt --open

# Combine flags
shrip ./dist/ -n release -c -o
```

**Example output:**

```
Compressing 3 items (4.8 MB) into project-handover.zip...
⠋ Compressing ████████████████████████████████████ 3/3 files
Compressed to 1.2 MB (75% smaller). Uploading...
⠋ Uploading   ████████████████████████████████████ 1.2/1.2 MB  850.3 kB/s

╭──────────── Ready to share ────────────╮
│                                        │
│  https://gofile.io/d/AbCd123           │
│                                        │
╰──────── Link copied! ─────────────────╯

(Files are automatically deleted after a period of inactivity.)
```

## Options

| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--name` | `-n` | Custom archive name (without `.zip`) | `shrip_archive` |
| `--copy` | `-c` | Copy the download link to clipboard | off |
| `--open` | `-o` | Open the download link in your browser | off |
| `--version` | `-v` | Show version and exit | |
| `--help` | | Show usage help | |

## How It Works

1. Validates that all provided paths exist.
2. Compresses everything into a temporary `.zip` archive — directories are walked recursively, preserving folder structure.
3. Uploads the archive to [gofile.io](https://gofile.io) (anonymous, no account needed, no file size limit).
4. Prints the download URL (and copies/opens it if requested).
5. Deletes the temporary zip file automatically — even if the upload fails or you hit Ctrl+C.

## License

MIT
