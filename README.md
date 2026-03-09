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

### Exclude patterns

Skip files and directories by glob pattern:

```bash
# Skip a single pattern
shrip ./my-project/ --exclude 'node_modules'

# Multiple patterns
shrip ./my-project/ -e 'node_modules' -e '*.log' -e '.env'

# .gitignore patterns are automatically respected
# Use .shripignore for additional patterns (same syntax)
echo '*.log' >> .shripignore
shrip ./my-project/

# Skip .shripignore and .gitignore processing
shrip ./my-project/ --no-ignore
```

### Preview before uploading

```bash
# See what would be archived without uploading
shrip ./my-project/ --dry-run

# Combine with exclude to fine-tune
shrip ./my-project/ --dry-run -e 'node_modules' -e '.git'
```

### Encryption

Protect archives with AES-256 encryption:

```bash
# Interactive password prompt
shrip secrets.txt --password

# Read password from a file
shrip secrets.txt --password-file keyfile.txt

# Read password from environment variable
SHRIP_PASSWORD=secret shrip secrets.txt --password-env
```

### Multiple upload services

```bash
# Default (gofile.io — no size limit, ~10 days retention)
shrip file.txt

# Upload to transfer.sh (14-day retention)
shrip file.txt --service transfer

# Upload to 0x0.st (512 MB limit, 30 days–1 year retention)
shrip file.txt --service 0x0

# List available services
shrip --list-services
```

### JSON output

Machine-readable output for scripting and CI/CD:

```bash
# JSON output
shrip file.txt --json

# Use with jq
URL=$(shrip file.txt --json | jq -r '.url')

# JSON dry run
shrip ./project/ --json --dry-run
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
│  SHA256: a1b2c3...                     │
│  MD5:    d4e5f6...  (gofile)           │
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
| `--exclude` | `-e` | Glob pattern to exclude (repeatable) | none |
| `--dry-run` | | Preview what would be archived | off |
| `--json` | | Output results as JSON | off |
| `--password` | `-p` | Encrypt archive with AES-256 (interactive prompt) | off |
| `--password-file` | | Read encryption password from a file | none |
| `--password-env` | | Read password from `SHRIP_PASSWORD` env var | off |
| `--service` | `-s` | Upload service: `gofile`, `transfer`, or `0x0` | `gofile` |
| `--list-services` | | List available upload services and exit | |
| `--no-ignore` | | Skip `.shripignore` and `.gitignore` processing | off |
| `--version` | `-v` | Show version and exit | |
| `--help` | | Show usage help | |

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SHRIP_NAME` | Default archive name | `SHRIP_NAME=build` |
| `SHRIP_FAST` | Enable fast mode | `SHRIP_FAST=1` |
| `SHRIP_COPY` | Auto-copy link to clipboard | `SHRIP_COPY=1` |
| `SHRIP_ZONE` | Default upload zone | `SHRIP_ZONE=eu` |
| `SHRIP_SERVICE` | Default upload service | `SHRIP_SERVICE=transfer` |
| `SHRIP_EXCLUDE` | Comma-separated exclude patterns | `SHRIP_EXCLUDE=*.log,.git` |
| `SHRIP_PASSWORD` | Encryption password (with `--password-env`) | `SHRIP_PASSWORD=secret` |
| `NO_COLOR` | Disable colored output | `NO_COLOR=1` |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (invalid path, upload failure, bad arguments) |
| `130` | Interrupted (Ctrl+C) |

## Upload Services

| Service | Max Size | Retention | Auth |
|---------|----------|-----------|------|
| **gofile.io** (default) | Unlimited | ~10 days inactive | No |
| **transfer.sh** | ~10 GB | 14 days | No |
| **0x0.st** | 512 MB | 30 days – 1 year | No |

## How It Works

1. Validates that all provided paths exist.
2. Checks disk space in the temp directory and warns if low.
3. Compresses everything into a temporary `.zip` archive — directories are walked recursively, preserving folder structure. Already-compressed formats (`.iso`, `.mp4`, `.zip`, `.jpg`, etc.) are stored without compression to save time. Files matching `--exclude` patterns, `.shripignore`, and `.gitignore` rules are skipped.
4. Uploads the archive to the selected service (anonymous, no account needed). Supports streaming upload for large files with minimal memory usage.
5. Prints the download URL with SHA256/MD5 checksums (and copies/opens it if requested).
6. Deletes the temporary zip file automatically — even if the upload fails or you hit Ctrl+C.

## License

MIT
