"""Minimal UniversalDRM viewer for one file.

    pip install -e ".[demo]"
    python examples/flask_demo.py path/to/file.pdf

Then open http://127.0.0.1:5050. The file is never sent to the browser, only watermarked page images.
"""
import mimetypes
import sys
from flask import Flask, abort, jsonify, render_template_string, request, send_file, send_from_directory
from io import BytesIO
import universal_drm

PATH = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
MIME = mimetypes.guess_type(PATH)[0] or "application/octet-stream"
KIND = universal_drm.kind(MIME) or sys.exit(f"{MIME} is not supported")
renderer = universal_drm.Renderer()
app = Flask(__name__)

PAGE = """<!doctype html><meta charset="utf-8"><title>UniversalDRM demo</title>
<link rel="stylesheet" href="/udrm/universal-drm.css">
<body style="background:#0e141b;color:#dde;font-family:sans-serif;max-width:900px;margin:24px auto;padding:0 16px">
<h1>UniversalDRM demo</h1><div id="viewer"></div>
<script src="/udrm/universal-drm.js"></script>
<script>UniversalDRM.mount(document.getElementById('viewer'), {
  kind: {{ kind|tojson }}, pages: {{ pages }}, pageUrl: i => `/page/${i}`,
  videoUrl: '/video', videoType: {{ mime|tojson }},
  watermark: {{ watermark|tojson }}, statusUrl: '/status', statusInterval: 10
});</script>"""


def watermark():
    return f"Demo viewer · {request.remote_addr}"


@app.get("/")
def index():
    pages = renderer.page_count(PATH, MIME) if KIND == "pages" else 0
    return render_template_string(PAGE, kind=KIND, pages=pages, mime=MIME, watermark=watermark())


@app.get("/page/<int:index>")
def page(index):
    try:
        data = renderer.render_page(PATH, MIME, index, watermark())
    except IndexError:
        abort(404)
    return send_file(BytesIO(data), mimetype="image/jpeg", max_age=0)


@app.get("/video")
def video():
    if KIND != "video":
        abort(404)
    return send_file(PATH, mimetype=MIME, conditional=True)


@app.get("/status")
def status():
    return jsonify(active=True)


@app.get("/udrm/<path:name>")
def assets(name):
    return send_from_directory(universal_drm.static_dir(), name)


if __name__ == "__main__":
    app.run(port=5050)
