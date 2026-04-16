#!/usr/bin/env python3
"""md-live: local markdown live preview server."""

import argparse
import asyncio
import mimetypes
import os
import signal
import sys
import time
import urllib.parse
import subprocess
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PORT = 4000
POLL_INTERVAL = 0.5   # seconds between file-change polls
EXIT_GRACE = 1.0      # seconds to wait after last client disconnects

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(".")
active_connections: set = set()
_exit_handle = None
_server = None
_loop = None

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def safe_resolve(base: Path, requested: str):
    """Resolve requested path and verify it stays inside base.
    Returns a Path on success, None if the path escapes or doesn't exist."""
    try:
        resolved = (base / requested).resolve()
        base_resolved = base.resolve()
        if not str(resolved).startswith(str(base_resolved) + os.sep) and resolved != base_resolved:
            return None
        if not resolved.is_file():
            return None
        return resolved
    except (ValueError, OSError):
        return None

# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_BASE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-light.min.css">
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 40px 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  .markdown-body {{ max-width: 900px; }}
  .back {{ display: inline-block; margin-bottom: 20px; color: #0366d6; text-decoration: none; font-size: 14px; }}
  .back:hover {{ text-decoration: underline; }}
  h1.dir-title {{ font-size: 20px; color: #444; margin-bottom: 16px; font-weight: 500; }}
  .file-list {{ list-style: none; padding: 0; margin: 0; }}
  .file-list li {{ padding: 4px 0; }}
  .file-list a {{ color: #0366d6; text-decoration: none; font-size: 15px; }}
  .file-list a:hover {{ text-decoration: underline; }}
  .file-list .icon {{ margin-right: 6px; }}
  .section-label {{ font-size: 12px; font-weight: 600; color: #888; text-transform: uppercase;
                    letter-spacing: .05em; margin: 16px 0 4px; }}
</style>
</head>
<body>
<div class="container">
{body}
</div>
{script}
</body>
</html>
"""

_VIEWER_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-light.min.css">
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  .viewer-layout {{ display: flex; min-height: 100vh; }}
  /* --- TOC sidebar --- */
  .toc-nav {{
    width: 220px; min-width: 220px; flex-shrink: 0;
    position: sticky; top: 0; height: 100vh; overflow-y: auto;
    border-right: 1px solid #e1e4e8; background: #fafbfc;
    transition: width 0.15s ease, min-width 0.15s ease;
  }}
  .toc-nav.collapsed {{ width: 36px; min-width: 36px; overflow: hidden; }}
  .toc-nav.collapsed .toc-inner {{ display: none; }}
  .toc-toggle {{
    display: block; width: 100%; padding: 10px 12px; border: none;
    background: none; cursor: pointer; font-size: 16px; color: #555;
    text-align: left; border-bottom: 1px solid #e1e4e8;
  }}
  .toc-toggle:hover {{ background: #f0f0f0; color: #000; }}
  .toc-nav.collapsed .toc-toggle {{ text-align: center; padding: 10px 0; }}
  .toc-inner {{ padding: 8px 0; }}
  .toc-heading {{ font-size: 11px; font-weight: 600; color: #888; text-transform: uppercase;
                  letter-spacing: .06em; padding: 4px 12px 8px; }}
  .toc-list {{ list-style: none; padding: 0; margin: 0; }}
  .toc-list li {{ line-height: 1.4; }}
  .toc-list a {{
    display: block; padding: 3px 12px; color: #444; text-decoration: none;
    font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .toc-list a:hover {{ color: #0366d6; background: #eef2f7; }}
  .toc-list a.active {{ color: #0366d6; font-weight: 600; }}
  .toc-h1 > a {{ font-weight: 600; color: #222; }}
  .toc-h2 > a {{ padding-left: 22px; }}
  .toc-h3 > a {{ padding-left: 36px; font-size: 12px; color: #666; }}
  /* --- Main content --- */
  .viewer-main {{ flex: 1; min-width: 0; padding: 40px 48px 80px; }}
  .back {{ display: inline-block; margin-bottom: 20px; color: #0366d6; text-decoration: none; font-size: 14px; }}
  .back:hover {{ text-decoration: underline; }}
  .markdown-body {{ max-width: 860px; }}
</style>
</head>
<body>
<div class="viewer-layout">
  <nav class="toc-nav" id="toc-nav">
    <button class="toc-toggle" id="toc-toggle" title="Toggle table of contents">&#9776;</button>
    <div class="toc-inner">
      <div class="toc-heading">Contents</div>
      <ul class="toc-list" id="toc-list"></ul>
    </div>
  </nav>
  <main class="viewer-main">
    <a class="back" href="/">&#8592; back</a>
    <article class="markdown-body" id="content"></article>
  </main>
</div>
{script}
</body>
</html>
"""

def _render_page(title, body, script=""):
    return _BASE_HTML.format(title=title, body=body, script=script)

def _listing_page(files):
    md_files  = [f for f in files if _is_markdown(f)]
    img_files = [f for f in files if _is_image(f)]
    other     = [f for f in files if not _is_markdown(f) and not _is_image(f)]

    rows = ['<h1 class="dir-title">&#128196; Files</h1>', '<ul class="file-list" id="file-list">']

    def add_section(label, items, icon):
        if not items:
            return
        rows.append(f'<li class="section-label">{label}</li>')
        for name in sorted(items):
            enc = urllib.parse.quote(name)
            rows.append(f'<li><span class="icon">{icon}</span>'
                        f'<a href="/view?f={enc}">{name}</a></li>')

    add_section("Markdown", md_files, "&#128221;")
    add_section("Images",   img_files, "&#128444;")
    if other:
        rows.append('<li class="section-label">Other</li>')
        for name in sorted(other):
            rows.append(f'<li><span class="icon">&#128196;</span>{name}</li>')

    rows.append('</ul>')
    body = "\n".join(rows)

    script = """\
<script>
(function() {
  var es = new EventSource('/events');
  es.addEventListener('update', function() {
    fetch('/fragment')
      .then(function(r) { return r.text(); })
      .then(function(html) {
        var el = document.getElementById('file-list');
        if (el) el.outerHTML = html;
      });
  });
})();
</script>"""
    return _render_page("md-live", body, script)

def _viewer_page(filename):
    enc = urllib.parse.quote(filename)
    script = f"""\
<script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
<script>
(function() {{
  var file = {repr(enc)};

  function buildTOC() {{
    var headings = document.querySelectorAll('#content h1, #content h2, #content h3');
    var list = document.getElementById('toc-list');
    var nav = document.getElementById('toc-nav');
    list.innerHTML = '';
    if (headings.length === 0) {{
      nav.classList.add('collapsed');
      return;
    }}
    headings.forEach(function(h, i) {{
      if (!h.id) h.id = 'heading-' + i;
      var level = parseInt(h.tagName[1], 10);
      var li = document.createElement('li');
      li.className = 'toc-h' + level;
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent;
      a.title = h.textContent;
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        h.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }});
      li.appendChild(a);
      list.appendChild(li);
    }});
  }}

  function loadContent() {{
    fetch('/raw?f=' + file)
      .then(function(r) {{ return r.text(); }})
      .then(function(md) {{
        document.getElementById('content').innerHTML = marked.parse(md);
        document.querySelectorAll('#content img').forEach(function(img) {{
          var src = img.getAttribute('src');
          if (src && !src.startsWith('http://') && !src.startsWith('https://') && !src.startsWith('/raw')) {{
            img.src = '/raw?f=' + encodeURIComponent(src);
          }}
        }});
        document.querySelectorAll('#content a[href]').forEach(function(a) {{
          a.target = '_blank';
          a.rel = 'noopener noreferrer';
        }});
        buildTOC();
      }});
  }}

  document.getElementById('toc-toggle').addEventListener('click', function() {{
    document.getElementById('toc-nav').classList.toggle('collapsed');
  }});

  loadContent();
  var es = new EventSource('/events?f=' + file);
  es.addEventListener('update', loadContent);
}})();
</script>"""
    return _VIEWER_HTML.format(title=filename, script=script)

def _image_page(filename):
    enc = urllib.parse.quote(filename)
    body = (f'<a class="back" href="/">&#8592; back</a>\n'
            f'<div style="text-align:center">'
            f'<img src="/raw?f={enc}" style="max-width:100%" id="img"></div>')
    script = f"""\
<script>
(function() {{
  var file = {repr(enc)};
  var es = new EventSource('/events?f=' + file);
  es.addEventListener('update', function() {{
    var img = document.getElementById('img');
    img.src = '/raw?f=' + file + '&t=' + Date.now();
  }});
}})();
</script>"""
    return _render_page(filename, body, script)

def _listing_fragment(files):
    """Return just the <ul> element for AJAX updates."""
    md_files  = [f for f in files if _is_markdown(f)]
    img_files = [f for f in files if _is_image(f)]
    other     = [f for f in files if not _is_markdown(f) and not _is_image(f)]

    rows = ['<ul class="file-list" id="file-list">']

    def add_section(label, items, icon):
        if not items:
            return
        rows.append(f'<li class="section-label">{label}</li>')
        for name in sorted(items):
            enc = urllib.parse.quote(name)
            rows.append(f'<li><span class="icon">{icon}</span>'
                        f'<a href="/view?f={enc}">{name}</a></li>')

    add_section("Markdown", md_files, "&#128221;")
    add_section("Images",   img_files, "&#128444;")
    if other:
        rows.append('<li class="section-label">Other</li>')
        for name in sorted(other):
            rows.append(f'<li><span class="icon">&#128196;</span>{name}</li>')

    rows.append('</ul>')
    return "\n".join(rows)

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

_MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".mkd"}
_IMAGE_EXTS    = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico"}

def _is_markdown(name: str) -> bool:
    return Path(name).suffix.lower() in _MARKDOWN_EXTS

def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in _IMAGE_EXTS

def _list_files(base: Path):
    try:
        return [e.name for e in base.iterdir()
                if e.is_file() and not e.name.startswith(".")]
    except OSError:
        return []

def _get_mtime(path) -> float:
    try:
        if isinstance(path, Path):
            return path.stat().st_mtime
        return os.stat(path).st_mtime
    except OSError:
        return 0.0

# ---------------------------------------------------------------------------
# HTTP parsing
# ---------------------------------------------------------------------------

async def _read_request(reader):
    """Read HTTP request headers. Returns (method, path, query, headers) or None."""
    try:
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
            if not chunk:
                return None
            raw += chunk
            if len(raw) > 16384:
                return None
        header_block = raw.split(b"\r\n\r\n", 1)[0].decode("utf-8", errors="replace")
        lines = header_block.split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2:
            return None
        method = parts[0]
        full_path = parts[1] if len(parts) > 1 else "/"
        if "?" in full_path:
            path, query = full_path.split("?", 1)
        else:
            path, query = full_path, ""
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        return method, path, query, headers
    except (asyncio.TimeoutError, UnicodeDecodeError, OSError):
        return None

# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

async def _send_response(writer, status: int, content_type: str, body: bytes, extra_headers=""):
    status_text = {200: "OK", 403: "Forbidden", 404: "Not Found",
                   405: "Method Not Allowed"}.get(status, "Unknown")
    response = (
        f"HTTP/1.1 {status} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"Cache-Control: no-cache\r\n"
        + extra_headers +
        "\r\n"
    ).encode() + body
    writer.write(response)
    await writer.drain()

async def _send_html(writer, html: str):
    await _send_response(writer, 200, "text/html; charset=utf-8", html.encode())

async def _send_error(writer, status: int, msg: str):
    await _send_response(writer, status, "text/plain; charset=utf-8", msg.encode())

# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def _handle_index(writer):
    files = _list_files(BASE_DIR)
    await _send_html(writer, _listing_page(files))

async def _handle_fragment(writer):
    files = _list_files(BASE_DIR)
    await _send_response(writer, 200, "text/html; charset=utf-8",
                         _listing_fragment(files).encode())

async def _handle_view(writer, query: str):
    params = urllib.parse.parse_qs(query)
    filename = params.get("f", [""])[0]
    if not filename:
        await _send_error(writer, 404, "Not found")
        return
    resolved = safe_resolve(BASE_DIR, filename)
    if resolved is None:
        await _send_error(writer, 404, "Not found")
        return
    if _is_image(filename):
        await _send_html(writer, _image_page(filename))
    else:
        await _send_html(writer, _viewer_page(filename))

async def _handle_raw(writer, query: str):
    params = urllib.parse.parse_qs(query)
    filename = params.get("f", [""])[0]
    if not filename:
        await _send_error(writer, 404, "Not found")
        return
    resolved = safe_resolve(BASE_DIR, filename)
    if resolved is None:
        await _send_error(writer, 403, "Forbidden")
        return
    try:
        data = resolved.read_bytes()
    except OSError:
        await _send_error(writer, 404, "Not found")
        return
    ct, _ = mimetypes.guess_type(str(resolved))
    if ct is None:
        ct = "application/octet-stream"
    await _send_response(writer, 200, ct, data)

async def _handle_events(writer, query: str):
    params = urllib.parse.parse_qs(query)
    filename = params.get("f", [""])[0]

    # Send SSE headers
    headers = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/event-stream\r\n"
        "Cache-Control: no-cache\r\n"
        "Connection: keep-alive\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "\r\n"
    ).encode()
    writer.write(headers)
    await writer.drain()

    # Determine what to watch
    if filename:
        resolved = safe_resolve(BASE_DIR, filename)
        watch_path = resolved  # may be None — we'll just watch a nonexistent file (mtime=0)
    else:
        watch_path = None  # watch directory

    _register_connection(writer)
    last_mtime = _get_mtime(watch_path if watch_path else BASE_DIR)

    try:
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            current = _get_mtime(watch_path if watch_path else BASE_DIR)
            if current != last_mtime:
                last_mtime = current
                writer.write(b"event: update\ndata: changed\n\n")
            else:
                # SSE comment — ignored by EventSource but causes a write,
                # so we detect client disconnects promptly even without changes.
                writer.write(b": keepalive\n\n")
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError, asyncio.CancelledError):
        pass
    finally:
        _unregister_connection(writer)

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _register_connection(writer):
    global _exit_handle
    active_connections.add(writer)
    if _exit_handle is not None:
        _exit_handle.cancel()
        _exit_handle = None

def _unregister_connection(writer):
    active_connections.discard(writer)
    if not active_connections:
        _schedule_exit()

def _schedule_exit():
    global _exit_handle
    if _exit_handle is not None:
        return
    _exit_handle = _loop.call_later(EXIT_GRACE, _do_exit)

def _do_exit():
    if _server:
        _server.close()
    sys.exit(0)

# ---------------------------------------------------------------------------
# Main server
# ---------------------------------------------------------------------------

async def _handle_connection(reader, writer):
    try:
        result = await _read_request(reader)
        if result is None:
            writer.close()
            return
        method, path, query, _headers = result

        if method != "GET":
            await _send_error(writer, 405, "Method not allowed")
        elif path == "/":
            await _handle_index(writer)
        elif path == "/fragment":
            await _handle_fragment(writer)
        elif path == "/view":
            await _handle_view(writer, query)
        elif path == "/raw":
            await _handle_raw(writer, query)
        elif path == "/events":
            await _handle_events(writer, query)
        else:
            await _send_error(writer, 404, "Not found")
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass

async def serve(port: int, directory: Path, open_browser: bool, open_file: str = "",
                port_explicit: bool = False):
    global BASE_DIR, _server, _loop

    BASE_DIR = directory
    _loop = asyncio.get_running_loop()

    if port_explicit:
        try:
            server = await asyncio.start_server(_handle_connection, "127.0.0.1", port)
        except OSError as e:
            print(f"Error: could not bind to port {port} — {e}", file=sys.stderr)
            print(f"Try a different port with --port.", file=sys.stderr)
            sys.exit(1)
    else:
        for candidate in range(port, port + 100):
            try:
                server = await asyncio.start_server(_handle_connection, "127.0.0.1", candidate)
                port = candidate
                break
            except OSError:
                continue
        else:
            print(f"Error: could not find a free port in range {port}–{port + 99}.", file=sys.stderr)
            sys.exit(1)

    if not open_browser and port != DEFAULT_PORT:
        print(f"Listening on port {port}", file=sys.stderr)

    _server = server
    _loop.add_signal_handler(signal.SIGINT, server.close)

    base_url = f"http://localhost:{port}"
    if open_file:
        url = base_url + "/view?f=" + urllib.parse.quote(open_file)
    else:
        url = base_url

    if open_browser:
        def _open_browser():
            # Call the OS launcher directly so we can silence its stdout/stderr.
            # "Opening in existing browser session." comes from the browser binary,
            # not our code, so webbrowser.open() can't suppress it.
            if sys.platform == "darwin":
                cmd = ["open", url]
            else:
                cmd = ["xdg-open", url]
            try:
                subprocess.Popen(cmd,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except OSError:
                webbrowser.open(url)  # fallback if xdg-open/open not found
        # Small delay so the server is ready before the browser hits it
        _loop.call_later(0.2, _open_browser)

    async with server:
        await server.serve_forever()

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="md-live",
        description="Live markdown preview server for local files.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Directory to serve, or a .md file to open directly (default: current directory)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_PORT,
        metavar="PORT",
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open browser automatically",
    )
    args = parser.parse_args()

    target = Path(args.path).resolve()
    if target.is_file():
        directory = target.parent
        open_file = target.name
    elif target.is_dir():
        directory = target
        open_file = ""
    else:
        print(f"Error: '{args.path}' is not a file or directory.")
        sys.exit(1)

    port_explicit = "--port" in sys.argv or "-p" in sys.argv
    asyncio.run(serve(args.port, directory, not args.no_open, open_file, port_explicit))

if __name__ == "__main__":
    main()
