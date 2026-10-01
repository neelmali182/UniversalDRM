"""UniversalDRM Command Line Interface.

Usage:
    udrm serve [--host 0.0.0.0] [--port 8000] [--reload]
    udrm view <file_path> [--host 0.0.0.0] [--port 5050]
    udrm <file_path>
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from io import BytesIO


def run_viewer(path: str, host: str = "0.0.0.0", port: int = 5050, watermark_text: str | None = None):
    """Launch the standalone capture-resistant viewer for a given file."""
    if not os.path.exists(path):
        print(f"[-] Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        from flask import Flask, abort, jsonify, render_template_string, request, send_file, send_from_directory
    except ImportError:
        print("[-] Flask is required for standalone viewing. Run: pip install flask", file=sys.stderr)
        sys.exit(1)

    import universal_drm

    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    kind = universal_drm.kind(mime)
    if not kind:
        print(f"[-] Error: {mime} is not supported for viewing.", file=sys.stderr)
        sys.exit(1)

    renderer = universal_drm.Renderer()
    app = Flask(__name__)

    PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UniversalDRM Viewer — {{ name }}</title>
<link rel="stylesheet" href="/udrm/universal-drm.css">
<style>
  body {
    background: #0b1118;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 24px 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .header {
    width: 100%;
    max-width: 900px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 12px;
  }
  .title { font-size: 1.25rem; font-weight: 600; color: #f8fafc; }
  .badge {
    background: #0369a1;
    color: #e0f2fe;
    font-size: 0.75rem;
    padding: 3px 8px;
    border-radius: 9999px;
    font-weight: 500;
  }
  #viewer { width: 100%; max-width: 900px; }
</style>
</head>
<body>
<div class="header">
  <div class="title">{{ name }}</div>
  <div class="badge">Capture-Resistant DRM</div>
</div>
<div id="viewer"></div>
<script src="/udrm/universal-drm.js"></script>
<script>
  UniversalDRM.mount(document.getElementById('viewer'), {
    kind: {{ kind|tojson }},
    pages: {{ pages }},
    pageUrl: i => `/page/${i}`,
    videoUrl: '/video',
    videoType: {{ mime|tojson }},
    watermark: {{ watermark|tojson }},
    statusUrl: '/status',
    statusInterval: 15
  });
</script>
</body>
</html>
"""

    def get_watermark():
        if watermark_text:
            return watermark_text
        return f"Viewer · {request.remote_addr}"

    @app.get("/")
    def index():
        pages = renderer.page_count(path, mime) if kind == "pages" else 0
        return render_template_string(
            PAGE_HTML,
            name=os.path.basename(path),
            kind=kind,
            pages=pages,
            mime=mime,
            watermark=get_watermark(),
        )

    @app.get("/page/<int:page_idx>")
    def page(page_idx):
        try:
            # Deliver clean baseline image so normal viewing is crisp & unwatermarked
            burn_opt = get_watermark() if request.args.get("burn") == "1" else None
            data = renderer.render_page(path, mime, page_idx, watermark=burn_opt)
        except IndexError:
            abort(404)
        return send_file(BytesIO(data), mimetype="image/jpeg", max_age=0)

    @app.get("/video")
    def video():
        if kind != "video":
            abort(404)
        return send_file(path, mimetype=mime, conditional=True)

    @app.get("/status")
    def status():
        return jsonify(active=True)

    @app.get("/udrm/<path:filename>")
    def static_assets(filename):
        return send_from_directory(universal_drm.static_dir(), filename)

    print(f"\n[✓] UniversalDRM Viewer serving: {path}")
    print(f"    URL: http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}")
    print(f"    Capture resistance: ACTIVE (Watermark revealed on screenshots & recordings)")
    app.run(host=host, port=port)


def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Launch the main UniversalDRM FastAPI API server."""
    try:
        import uvicorn
    except ImportError:
        print("[-] Uvicorn is required to run the API server. Run: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    display_host = "localhost" if host == "0.0.0.0" else host
    print(f"\n[+] UniversalDRM API Server Running!")
    print(f"    --> Open in browser: http://{display_host}:{port}")
    print(f"    --> Interactive Docs: http://{display_host}:{port}/docs\n")
    uvicorn.run("apps.api.main:app", host=host, port=port, reload=reload)


def main():
    parser = argparse.ArgumentParser(
        prog="udrm",
        description="UniversalDRM — Browser-first capture-resistant content protection.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start the UniversalDRM API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code change")

    # View command
    view_parser = subparsers.add_parser("view", help="View a file with instant capture-resistant DRM")
    view_parser.add_argument("path", help="Path to PDF, image, text, or video file")
    view_parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    view_parser.add_argument("--port", type=int, default=5050, help="Port to listen on (default: 5050)")
    view_parser.add_argument("--watermark", default=None, help="Custom watermark text")

    # If first argument looks like a file path, treat as view command
    if len(sys.argv) > 1 and sys.argv[1] not in ("serve", "view", "-h", "--help"):
        if os.path.exists(sys.argv[1]):
            sys.argv.insert(1, "view")

    args = parser.parse_args()

    if args.command == "serve":
        run_server(host=args.host, port=args.port, reload=args.reload)
    elif args.command == "view":
        run_viewer(path=args.path, host=args.host, port=args.port, watermark_text=args.watermark)
    else:
        # Default behavior with no arguments: start API server
        run_server()


if __name__ == "__main__":
    main()
