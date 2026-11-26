<img width="1366" height="768" alt="screenshot-2026-11-25_21-23-54" src="https://github.com/user-attachments/assets/d581800c-dca5-46d9-80ec-74743d3d6440" />
# lyrics-cli

Terminal lyrics viewer for Linux using `playerctl` and [LRCLIB](https://lrclib.net). Built as a personal replacement for `sptlrx`.

> **Note:** First repository, built with AI assistance while I learn Go and Python.

## Architecture

- **Go (`main.go`):** Fetches and parses synced LRC lyrics from LRCLIB.
- **Python (`frontend/`):** Handles `playerctl` metadata and playback sync, and renders the `curses` TUI.

## Dependencies

- `go`
- `python3`
- `playerctl`

## Usage

**NixOS / Nix:**
```bash
nix-shell
python3 frontend/main.py
```

**Other Linux distros:**
Install `go`, `python3`, and `playerctl` via your package manager, then run:
```bash
git clone https://github.com
cd lyrics-cli
python3 frontend/main.py
```

No manual compilation is needed—the frontend automatically falls back to `go run .` if no binary is present (run `go build` optionally for faster track switching).

## Compatibility

Tested on **Firefox (YouTube)** and **Spotify**. Should work with any MPRIS-compatible player supported by `playerctl`.

[![License: GPL v3](https://shields.io)(https://www.gnu.org/licenses/gpl.txt)]

This project is licensed under the GNU General Public License v3.0. Any forks or derivative works must remain open source under the same license.
