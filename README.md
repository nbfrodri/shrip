# shrip

**Zip and share files from the terminal — no browser needed.**

`shrip` bundles files and folders into a compressed archive and uploads it to [gofile.io](https://gofile.io), giving you a temporary public download link instantly. No accounts, no configuration, no context-switching.

## Installation

**From PyPI (recommended):**

```bash
pip install shrip
```

**With [pipx](https://pipx.pypa.io/) (isolated install):**

```bash
pipx install shrip
```

**From GitHub:**

```bash
pip install git+https://github.com/nbfrodri/shrip.git
```

> Requires Python 3.9 or higher. Works on Windows, macOS, and Linux.

## Usage

```bash
# Share a single file
shrip report.pdf

# Share multiple files and folders
shrip ./src/ README.md logo.png --name project-handover

# Custom archive name
shrip ./build/ -n release-v2
```

**Example output:**

```
Compressing 3 items into project-handover.zip...
⠋ Compressing ████████████████████████████████████ 3/3 files
Uploading to gofile.io...
⠋ Uploading   ████████████████████████████████████ 1.2/1.2 MB  850.3 kB/s

Success! Your file is live:
https://gofile.io/d/AbCd123

(Files are automatically deleted after a period of inactivity.)
```

## Options

| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--name` | `-n` | Custom archive name (without `.zip`) | `shrip_archive` |
| `--version` | `-v` | Show version and exit | |
| `--help` | | Show usage help | |

## How It Works

1. Validates that all provided paths exist.
2. Compresses everything into a temporary `.zip` archive — directories are walked recursively, preserving folder structure.
3. Uploads the archive to [gofile.io](https://gofile.io) (anonymous, no account needed, no file size limit).
4. Prints the download URL.
5. Deletes the temporary zip file automatically — even if the upload fails or you hit Ctrl+C.

## License

MIT
