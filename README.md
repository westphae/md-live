# md-live

Live markdown preview in your browser, straight from the terminal.

```
md-live &
```

That's it. A browser tab opens showing your directory. Click any `.md` file to render it. Edit in your favorite editor — the browser updates automatically whenever you save.

## Features

- **Live reload** — browser updates within a second of each file save, no manual refresh
- **File browser** — lists all files on startup; updates live as files are added
- **Table of contents** — collapsible sidebar built from `#`, `##`, `###` headings
- **Image support** — inline images in markdown render correctly; clicking an image file displays it directly
- **Auto-exit** — server shuts down when you close the browser tab
- **Zero dependencies** — single Python file, no `pip install` needed

## Installation

**With uv (recommended):**

```bash
uv tool install .
```

**With pip:**

```bash
pip install .
```

**Manually** — copy `md_live.py` somewhere on your `$PATH`:

```bash
cp md_live.py ~/.local/bin/md-live
chmod +x ~/.local/bin/md-live
```

Requires Python 3.8+.

## Usage

```
md-live [--port PORT] [--no-open] [PATH]
```

Run in the background from any directory:

```bash
cd ~/notes
md-live &
```

Or open a specific file directly:

```bash
md-live ~/notes/todo.md &
```

A browser tab opens at `http://localhost:4000`. When you close the tab, the server exits and the shell job finishes on its own.

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--port`, `-p` | `4000` | Port to listen on |
| `--host`, `-H` | `127.0.0.1` | Address to bind (use `0.0.0.0` to expose on the network) |
| `--no-open` | — | Don't open the browser automatically |
| `PATH` | `.` | Directory to serve, or a file to open directly |

## Configuration

Persistent defaults can be set in `~/.config/md-live/config`:

```ini
# md-live configuration
host = 0.0.0.0
port = 4001
no_open = true
```

Any key can be omitted to keep the built-in default. CLI flags always take precedence.

## Tips

For the smoothest experience, enable auto-save in your editor so the preview updates as you type:

- **VS Code** — `"files.autoSave": "afterDelay"`
- **Vim/Neovim** — `:set autowrite` or a `CursorHold` autocmd
- **Emacs** — `auto-save-visited-mode`
