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

Copy `md_live.py` somewhere on your `$PATH` and make it executable:

```bash
cp md_live.py ~/.local/bin/md-live
chmod +x ~/.local/bin/md-live
```

Requires Python 3.6+.

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
| `--no-open` | — | Don't open the browser automatically |
| `PATH` | `.` | Directory to serve, or a file to open directly |

## Tips

For the smoothest experience, enable auto-save in your editor so the preview updates as you type:

- **VS Code** — `"files.autoSave": "afterDelay"`
- **Vim/Neovim** — `:set autowrite` or a `CursorHold` autocmd
- **Emacs** — `auto-save-visited-mode`
