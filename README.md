# UniversalDRM

Let people view PDFs, images, text files and videos in an ordinary browser without handing them the file.

Documents are turned into page images on the server, with a watermark burned into the pixels. The browser draws those images on canvases. There is no PDF to save, no image to right-click, and no text to copy, and every screenshot or photo carries the watermark.

Used by [ForceX](https://github.com/eklavya2201/ForceX) for browser viewing.

## What it protects against

| Attempt | Result |
|---|---|
| Right-click → Save image, drag the image out | Blocked: content is drawn on canvases |
| Select and copy text | Blocked: text is rendered as pixels |
| Ctrl+P / browser Print | Blocked or prints blank |
| Ctrl+S, Ctrl+U, F12, Ctrl+Shift+I | Blocked (deterrent) |
| Download the original from the network tab | Not possible for documents: only watermarked JPEGs are sent |
| Remove the watermark in developer tools | Not possible for documents: it is part of the pixels |
| Switch window or open the Snipping Tool | Content blurs while the window is not focused |
| Print Screen key | Content blurs and the clipboard is cleared where the browser allows it |
| Sender revokes access or the session expires | Content is wiped from the screen at the next status check |

## What it cannot protect against

No website can block the operating system's screenshot tools or a camera. The only in-browser exceptions are the DRM systems built into browsers (Widevine, PlayReady, FairPlay), which cover video only and require a license from Google, Microsoft or Apple. UniversalDRM does not use them.

So a determined viewer **can** capture what is on screen, for example with a phone camera, a screen recorder started beforehand, or Win+Shift+S timed quickly. What they capture carries the watermark, which is the point: it identifies who leaked it.

For videos, the file itself is streamed to the browser, so the watermark is drawn over the player rather than burned into the frames.

If you need capture to be blocked outright, view the content in a native app instead. On Windows, `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` removes a window from screenshots and recordings. The ForceX desktop app does this.

## Supported content

| Type | MIME types | How it is shown |
|---|---|---|
| PDF | `application/pdf` | One watermarked JPEG per page, loaded as you scroll |
| Images | `image/png`, `image/jpeg`, `image/gif`, `image/webp` | One watermarked JPEG (first frame for animations) |
| Text | `text/plain` | Rendered onto A4 pages |
| Video | `video/*` the browser can play | Streamed, with a live watermark over the player |

Office files and other formats are not rendered.

## Install

```bash
pip install "universal-drm @ git+https://github.com/neelmali182/UniversalDRM@v0.1.0"
```

Requires Python 3.10+. Dependencies are Pillow and pypdfium2, both with prebuilt wheels, so no system packages are needed.

## Usage

### Server (Python)

```python
import universal_drm

renderer = universal_drm.Renderer()           # max_side=2000, pdf_scale=2.0, jpeg_quality=82

universal_drm.kind("application/pdf")          # 'pages', 'video' or None
renderer.page_count(path, "application/pdf")   # number of pages
renderer.render_page(path, "application/pdf", 0, "alice@example.com · #1a2b")  # JPEG bytes; IndexError past the end

universal_drm.static_dir()                     # folder with universal-drm.js and universal-drm.css to serve
```

Serve each page from a route that checks the viewer's session, and send `Cache-Control: no-store`.

### Browser (JavaScript)

```html
<link rel="stylesheet" href="/udrm/universal-drm.css">
<div id="viewer"></div>
<script src="/udrm/universal-drm.js"></script>
<script>
  const viewer = UniversalDRM.mount(document.getElementById('viewer'), {
    kind: 'pages',                       // or 'video'
    pages: 12,
    pageUrl: i => `/doc/page/${i}`,
    videoUrl: '/doc/video', videoType: 'video/mp4',
    watermark: 'alice@example.com · #1a2b',
    statusUrl: '/doc/status',            // must answer {"active": true}; anything else ends the session
    statusInterval: 15,
    onEnd: reason => console.log('ended:', reason)
  });
  // viewer.destroy() wipes the content
</script>
```

The script has no dependencies and works under a strict Content Security Policy (`script-src 'self'`). Put the `mount` call in your own script file if your policy forbids inline scripts.

### Demo

```bash
pip install -e ".[demo]"
python examples/flask_demo.py path/to/file.pdf
```

Open http://127.0.0.1:5050.

## Development

```bash
pip install -e ".[test]"
pytest
```

## License

MIT
