# shrip

**Zip and share files from the terminal — no browser needed.**

`shrip` bundles files and folders into a compressed archive and uploads it to [gofile.io](https://gofile.io), giving you a temporary public download link instantly. No accounts, no configuration, no context-switching.

## Installation

**Ubuntu / Debian:**

```bash
sudo apt install pipx
pipx ensurepath   # adds ~/.local/bin to PATH (one-time setup, restart terminal after)
pipx install shrip
```

**macOS:**

```bash
brew install pipx
pipx ensurepath
pipx install shrip
```

**Windows:**

```bash
pip install pipx
pipx ensurepath
pipx install shrip
```

**With pip (any OS):**

```bash
pip install shrip
```

> On Ubuntu 23.04+ and other modern distros, `pip install` is blocked by default to protect the system Python. Use `pipx` instead — it installs `shrip` in an isolated environment and adds it to your PATH automatically.

**From GitHub:**

```bash
pip install git+https://github.com/nbfrodri/shrip.git
```

> Requires Python 3.9 or higher. Works on Windows, macOS, and Linux.

## Updating

```bash
# If installed with pipx
pipx upgrade shrip

# If installed with pip
pip install --upgrade shrip
```

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

# Skip compression (faster for ISOs, videos, archives, etc.)
shrip ubuntu.iso --fast

# Upload to a specific region (eu or na)
shrip bigfile.tar.gz --zone na

# Combine flags
shrip ./dist/ -n release -c -o
```

**Example output:**

```
Compressing 3 items (4.8 MB) into project-handover.zip...
⠋ Compressing ████████████████████████████████████ 100% 4.8/4.8 MB
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
| `--fast` | `-f` | Skip compression (faster for pre-compressed files) | off |
| `--zone` | `-z` | Upload region: `eu` (Europe) or `na` (North America) | auto |
| `--version` | `-v` | Show version and exit | |
| `--help` | | Show usage help | |

## How It Works

1. Validates that all provided paths exist.
2. Compresses everything into a temporary `.zip` archive — directories are walked recursively, preserving folder structure. Already-compressed formats (`.iso`, `.mp4`, `.zip`, `.jpg`, etc.) are stored without compression to save time.
3. Uploads the archive to [gofile.io](https://gofile.io) (anonymous, no account needed, no file size limit). Supports streaming upload for large files with minimal memory usage.
4. Prints the download URL (and copies/opens it if requested).
5. Deletes the temporary zip file automatically — even if the upload fails or you hit Ctrl+C.

## License

MIT
