# shrip

Zip and share files from the terminal — no browser needed.

`shrip` bundles files and folders into a compressed archive and uploads it to [gofile.io](https://gofile.io), giving you a temporary public download link instantly.

## Installation

```bash
pip install shrip
```

Or with [pipx](https://pipx.pypa.io/) for an isolated install:

```bash
pipx install shrip
```

Or directly from GitHub:

```bash
pip install git+https://github.com/nbfrodri/shrip.git
```

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
Validating paths...
Compressing 3 items into project-handover.zip...
[####################################] 100%
Uploading to gofile.io...
[####################################] 100%

Success! Your file is live:
https://gofile.io/d/AbCd123

(Files are automatically deleted after a period of inactivity.)
```

## Options

| Flag        | Short | Description                          | Default         |
| ----------- | ----- | ------------------------------------ | --------------- |
| `--name`    | `-n`  | Custom archive name (without `.zip`) | `shrip_archive` |
| `--version` | `-v`  | Show version and exit                |                 |
| `--help`    |       | Show usage help                      |                 |

## How It Works

1. Validates that all provided paths exist.
2. Compresses everything into a temporary `.zip` archive (directories are walked recursively, preserving folder structure).
3. Uploads the archive to [gofile.io](https://gofile.io) (anonymous, no account needed).
4. Returns the download URL.
5. Deletes the temporary zip file automatically.

## Requirements

- Python 3.9+

## License

MIT
