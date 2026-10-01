<div align="center">

# UniversalDRM

**Capture-resistant document, image, text and video viewing in an ordinary browser, without handing the recipient the file.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#project-status)
[![Security Model](https://img.shields.io/badge/security-honest%20by%20design-success.svg)](#security-model)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

[Overview](#overview) ·
[How It Works](#how-it-works) ·
[Security Model](#security-model) ·
[Install](#installation) ·
[Quick Start](#quick-start) ·
[API Reference](#api-reference) ·
[Roadmap](#roadmap) ·
[Contributing](#contributing)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [How It Works](#how-it-works)
- [Security Model](#security-model)
  - [What it protects against](#what-it-protects-against)
  - [What it cannot protect against](#what-it-cannot-protect-against)
  - [Enforcement classes](#enforcement-classes)
- [Supported Content](#supported-content)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Integration Guide](#integration-guide)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Development](#development)
- [Production Checklist](#production-checklist)
- [Project Status](#project-status)
- [Roadmap](#roadmap)
- [Security Policy](#security-policy)
- [Contributing](#contributing)
- [FAQ](#faq)
- [License](#license)

---

## Overview

UniversalDRM lets an application show sensitive content to a recipient **inside the browser** while never giving them the original file.

Documents are rasterized **on the server** and drawn onto `<canvas>` elements; the original file and text layer are not sent to the browser. Integrations may burn a visible watermark into server-rendered pixels. The standalone viewer instead displays clean pages and adds a temporary watermark only when browser-visible capture signals fire. That detection is best-effort: an OS recorder or camera can capture a page without a watermark.

> **Design philosophy:** make casual extraction impractical, make every capture traceable, and be explicit about what a website cannot do. UniversalDRM does not claim to block screenshots. No browser-only system can.

Used by [ForceX](https://github.com/eklavya2201/ForceX) for browser viewing.

## Key Features

| Area | Capability |
|---|---|
| **Server-side rendering** | PDFs, images and text are converted to watermarked JPEG pages on the server. The original never reaches the browser. |
| **Burned-in watermark** | The watermark is part of the pixels, not a DOM overlay, so it cannot be removed in developer tools. |
| **Canvas viewer** | Content is drawn on canvases: no selectable text, no draggable image, no save-as target. |
| **Deterrence layer** | Blocks context menu, drag, copy, print, and common save/inspect shortcuts. Clearly documented as deterrence. |
| **Capture heuristics** | Content blurs when the window loses focus; clipboard is cleared on Print Screen where the browser permits. |
| **Live revocation** | The viewer polls a status endpoint and wipes content when the session is revoked or expired. |
| **Lazy page loading** | Pages are requested as the user scrolls, which keeps bandwidth and server load proportional to actual reading. |
| **Video support** | Streams browser-playable video with a live watermark over the player. |
| **Zero-dependency frontend** | A single JS file and a single CSS file. Works under a strict CSP (`script-src 'self'`). |
| **Framework-agnostic** | A small Python library with no web framework dependency. Works with Flask, FastAPI, Django, or anything that can serve bytes. |
| **Light install** | Dependencies are Pillow and pypdfium2, both with prebuilt wheels. No system packages required. |

## How It Works

```text
            SERVER (trusted)                               BROWSER (untrusted)
 ┌───────────────────────────────────┐           ┌───────────────────────────────┐
 │                                   │           │                               │
 │  original file (private storage)  │           │   UniversalDRM viewer (JS)    │
 │              │                    │           │                               │
 │              ▼                    │           │   - requests page N           │
 │   Renderer.render_page(...)       │  page N   │   - draws JPEG on <canvas>    │
 │   - rasterize (pypdfium2/Pillow)  │ ────────▶ │   - deterrence layer          │
 │   - burn watermark into pixels    │  (JPEG,   │   - blur on focus loss        │
 │   - encode JPEG                   │ no-store) │   - polls status endpoint     │
 │              ▲                    │           │                               │
 │              │                    │  status   │                               │
 │   YOUR app: session + auth check  │ ◀──────── │   {"active": true}            │
 │                                   │           │   anything else ⇒ wipe        │
 └───────────────────────────────────┘           └───────────────────────────────┘
```

**Request lifecycle**

1. Your application authenticates the viewer and creates a session (your code).
2. The browser mounts the viewer with a `pageUrl` function and a watermark label.
3. For each visible page, the browser requests `pageUrl(i)`.
4. Your route validates the session, then calls `Renderer.render_page(...)` with the viewer's watermark text.
5. The server returns JPEG bytes with `Cache-Control: no-store`.
6. The viewer draws the image onto a canvas. No file, text or vector data ever reaches the client.
7. Every `statusInterval` seconds the viewer calls `statusUrl`. Anything other than `{"active": true}` ends the session and wipes the screen.

## Security Model

UniversalDRM separates **what the server enforces** from **what the browser merely discourages**, so integrators never mistake one for the other.

### What it protects against

| Attempt | Result |
|---|---|
| Right-click → Save image, drag the image out | **Blocked:** content is drawn on canvases |
| Select and copy text | **Blocked:** text is rendered as pixels |
| Ctrl+P / browser Print | **Blocked** or prints blank |
| Ctrl+S, Ctrl+U, F12, Ctrl+Shift+I | **Blocked** (deterrent) |
| Download the original from the network tab | **Not possible** for documents: only watermarked JPEGs are sent |
| Remove the watermark in developer tools | **Not possible** for documents: it is part of the pixels |
| Switch window or open the Snipping Tool | Content **blurs** while the window is not focused |
| Print Screen key | Content **blurs** and the clipboard is cleared where the browser allows it |
| Sender revokes access or the session expires | Content is **wiped** from the screen at the next status check |

### What it cannot protect against

No website can block the operating system's screenshot tools or a camera. The only in-browser exceptions are the DRM systems built into browsers (Widevine, PlayReady, FairPlay). They cover **video only** and require a license from Google, Microsoft or Apple. UniversalDRM does not use them.

A determined viewer **can** still capture what is on screen, for example with:

- a phone camera pointed at the display,
- a screen recorder started beforehand,
- a well-timed OS snipping shortcut (such as Win+Shift+S).

When the viewer detects a capture-related signal, it briefly overlays the viewer identity. A recorder started before viewing, unsupported capture software, or a camera may not trigger that overlay, so captures are not guaranteed to carry a watermark.

**Video is weaker than documents.** The video file itself is streamed to the browser, so the watermark is drawn *over the player* rather than burned into the frames. A viewer can remove an overlay. Treat video protection as deterrence plus access control.

**If capture must be blocked outright,** use a native viewer. On Windows, `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` removes a window from screenshots and recordings. The ForceX desktop app does this.

### Enforcement classes

Every protection falls into one of three classes. Keep this distinction in your own product copy.

| Class | Meaning | Examples in UniversalDRM |
|---|---|---|
| **Enforced** | The server refuses, even against a hostile client. | No original-file endpoint exists; session status checks; access revocation (via your app) |
| **Best-effort** | Client-side deterrence. A determined user with DevTools can bypass it. | Shortcut blocking, context-menu blocking, blur-on-blur, clipboard clearing, print suppression |
| **Traceability** | Does not prevent capture; may identify the source. | Server-burned watermark when enabled; temporary client overlay on detected capture signals |

### Threat summary

| Threat | Mitigation | Residual risk |
|---|---|---|
| Casual save/copy/print | Canvas rendering, deterrence layer | Low |
| Network-tab scraping of originals | Originals never sent; authorized sessions receive rendered page images | Medium: page images can still be fetched by an authorized client |
| Watermark removal | Server-burned watermark only when enabled | Depends on the rendering integration |
| Link/session sharing | **Your app** must bind sessions to identity (see [Integration Guide](#integration-guide)) | Depends on your auth |
| Bulk page scraping with a valid session | **Your app** should rate-limit page requests per session | Medium without rate limits |
| Screenshot / photo / screen recording | Best-effort overlay on detected signals | Not reliably detectable or preventable in-browser; captures may be unwatermarked |
| Cache reuse of page images | `Cache-Control: no-store` (your route) | Low if configured |

## Supported Content

| Type | MIME types | How it is shown |
|---|---|---|
| PDF | `application/pdf` | One watermarked JPEG per page, loaded as you scroll |
| Images | `image/png`, `image/jpeg`, `image/gif`, `image/webp` | One watermarked JPEG (first frame for animations) |
| Text | `text/plain` | Rendered onto A4 pages |
| Video | `video/*` that the browser can play | Streamed, with a live watermark over the player |

Office files (DOCX, PPTX, XLSX) and other formats are **not rendered**. See the [Roadmap](#roadmap).

## Installation

```bash
pip install "universal-drm @ git+https://github.com/neelmali182/UniversalDRM@v0.1.0"
```

**Requirements**

- Python 3.11 or newer
- Pillow and pypdfium2 (installed automatically, prebuilt wheels, no system packages)

## Quick Start

### 1. Server (Python)

```python
import universal_drm

renderer = universal_drm.Renderer()   # defaults: max_side=2000, pdf_scale=2.0, jpeg_quality=82

mime = "application/pdf"
path = "/private/storage/report.pdf"

universal_drm.kind(mime)                  # -> 'pages', 'video' or None
renderer.page_count(path, mime)           # -> number of pages

jpeg: bytes = renderer.render_page(
    path, mime, 0,                        # page index (0-based)
    "alice@example.com · #1a2b",          # watermark text burned into pixels
)                                         # raises IndexError past the last page

universal_drm.static_dir()                # folder containing universal-drm.js and universal-drm.css
```

Serve each page from a route that **checks the viewer's session** and responds with `Cache-Control: no-store`.

### 2. Browser (JavaScript)

```html
<link rel="stylesheet" href="/udrm/universal-drm.css">
<div id="viewer"></div>

<script src="/udrm/universal-drm.js"></script>
<script>
  const viewer = UniversalDRM.mount(document.getElementById('viewer'), {
    kind: 'pages',                          // or 'video'
    pages: 12,
    pageUrl: i => `/doc/page/${i}`,
    videoUrl: '/doc/video',
    videoType: 'video/mp4',
    watermark: 'alice@example.com · #1a2b',
    statusUrl: '/doc/status',               // must answer {"active": true}; anything else ends the session
    statusInterval: 15,                     // seconds
    onEnd: reason => console.log('ended:', reason)
  });

  // viewer.destroy()  // wipes the content
</script>
```

> The script has no dependencies and works under a strict Content Security Policy (`script-src 'self'`). If your policy forbids inline scripts, move the `mount` call into your own script file.

### 3. Run the demo

```bash
pip install -e ".[demo]"
python examples/flask_demo.py path/to/file.pdf
```

Open <http://127.0.0.1:5050>.

## Integration Guide

UniversalDRM is the **rendering and viewing layer**. It deliberately does not own authentication, sharing, or storage, so it can slot into your existing system. Your application is responsible for the following.

### Required (server-enforced protections depend on these)

| Responsibility | Why it matters |
|---|---|
| **Authenticate the viewer** and bind the session to a verified identity | Without identity, the watermark cannot identify a leaker. A forwarded link becomes an anonymous recipient. |
| **Authorize every page request** | `render_page` performs no access checks. Your route must. |
| **Keep originals private** | Store files outside any public path or public bucket. |
| **Send `Cache-Control: no-store`** on page and video responses | Prevents browser/proxy caches from retaining page images. |
| **Implement `statusUrl`** | Returns `{"active": true}` only while the session is valid, unexpired, and not revoked. |
| **Use HTTPS** | Protects tokens and content in transit. |

### Strongly recommended

| Responsibility | Why it matters |
|---|---|
| **Rate-limit page requests per session** | A valid session can otherwise fetch every page image in seconds. |
| **Short session lifetimes** with re-authentication | Limits the window of exposure if a session is shared. |
| **Watermark with verified identity + short session id + timestamp** | Makes leaks attributable and time-bounded. |
| **Do not consume one-time links on `GET`** | Email and chat link scanners prefetch URLs and would burn the link. Create the session on an explicit user action (`POST`). |
| **Audit page views and status failures** | Gives you a trail for incident response. |
| **Restrictive security headers** (CSP, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors`) | Reduces XSS and embedding risk. |

### Example route shape (framework-agnostic)

```python
def serve_page(request, doc_id, index):
    session = require_valid_session(request)          # YOUR auth + revocation + expiry checks
    doc = load_document_for(session, doc_id)          # YOUR authorization + private storage

    try:
        jpeg = renderer.render_page(
            doc.path, doc.mime, index,
            watermark_text(session)                   # e.g. "alice@example.com · #1a2b · 2026-09-30 22:45"
        )
    except IndexError:
        return not_found()

    return response(
        jpeg,
        content_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
```

## API Reference

### Python

#### `universal_drm.Renderer(max_side=2000, pdf_scale=2.0, jpeg_quality=82)`

Creates a renderer.

| Parameter | Default | Description |
|---|---|---|
| `max_side` | `2000` | Maximum pixel length of the longest side of an output image. Lower it to reduce bandwidth and fidelity. |
| `pdf_scale` | `2.0` | Rasterization scale for PDF pages. |
| `jpeg_quality` | `82` | JPEG encoding quality (1–100). |

#### `Renderer.page_count(path, mime) -> int`

Returns the number of renderable pages for the file.

#### `Renderer.render_page(path, mime, index, watermark) -> bytes`

Renders page `index` (0-based) and returns JPEG bytes with `watermark` burned into the pixels. Raises `IndexError` if `index` is past the last page.

#### `universal_drm.kind(mime) -> 'pages' | 'video' | None`

Classifies a MIME type. `None` means the type is not supported.

#### `universal_drm.static_dir() -> str`

Returns the path of the directory containing `universal-drm.js` and `universal-drm.css`, for mounting at a static route.

### JavaScript

#### `UniversalDRM.mount(element, options) -> viewer`

| Option | Type | Description |
|---|---|---|
| `kind` | `'pages' \| 'video'` | Viewer mode. |
| `pages` | `number` | Page count (for `kind: 'pages'`). |
| `pageUrl` | `(i: number) => string` | URL of the watermarked JPEG for page `i`. |
| `videoUrl` | `string` | Video source URL (for `kind: 'video'`). |
| `videoType` | `string` | Video MIME type, for example `video/mp4`. |
| `watermark` | `string` | Text drawn as the live watermark (video) and shown in the UI. |
| `statusUrl` | `string` | Endpoint polled for session validity. Must return `{"active": true}` to continue. |
| `statusInterval` | `number` | Polling interval in seconds. |
| `onEnd` | `(reason: string) => void` | Called when the session ends. |

**Returns** a `viewer` object with `viewer.destroy()`, which wipes the content and stops polling.

## Configuration

Rendering behavior is configured through the `Renderer` constructor (see above). An annotated [`.env.example`](.env.example) is provided for the demo and for integrators building a service around the library. Do not commit real secrets.

| Tuning goal | Adjust |
|---|---|
| Smaller responses, faster loads | Lower `max_side`, `jpeg_quality` |
| Sharper text in PDFs | Raise `pdf_scale` (increases CPU and size) |
| Stronger deterrence against scraping | Rate-limit at your route; shorten `statusInterval` |

## Architecture

UniversalDRM is intentionally small and layered:

```text
┌────────────────────────────────────────────┐
│ Your application                           │
│  auth · sharing · storage · audit · limits │   <- you own this
├────────────────────────────────────────────┤
│ universal_drm (Python)                     │
│  Renderer · kind() · static_dir()          │   <- rasterize + burn watermark
├────────────────────────────────────────────┤
│ universal-drm.js / .css (browser)          │
│  canvas viewer · deterrence · status poll  │   <- draw + discourage + wipe
└────────────────────────────────────────────┘
```

**Design decisions**

- **Server-side rasterization.** Sending pixels instead of files is what makes "no original in the browser" an enforced property, not a hope.
- **Watermark in pixels.** Overlays can be deleted in DevTools. Burned-in marks cannot.
- **Canvas, not DOM.** Removes the text layer and image element that copy/save rely on.
- **Stateless renderer.** No sessions or storage inside the library, so it composes with any auth model and scales horizontally.
- **No runtime frontend dependencies.** A single audited file, easy to CSP-lock and review.
- **Honest claims.** Protections are labelled enforced, best-effort, or traceability.

## Project Structure

```text
UniversalDRM/
├── universal_drm/        # Python package: Renderer, kind(), static_dir(), browser assets
├── examples/             # Runnable demos (Flask)
├── tests/                # Test suite (pytest)
├── apps/  packages/      # Scaffolding for the planned platform (API, viewer app, shared packages)
├── sdk/                  # Reserved for client SDKs
├── docker/               # Container definitions
├── docker-compose.yml    # Local development services
├── pyproject.toml        # Package metadata and extras ([demo], [test])
├── .env.example          # Example configuration
├── LICENSE               # MIT
└── README.md
```

The long-form design for the full platform (identity-bound shares, sessions, policy engine, forensic watermarking, media DRM) is in [`docs/implementation_plan.md`](docs/implementation_plan.md).

## Development

```bash
git clone https://github.com/neelmali182/UniversalDRM.git
cd UniversalDRM

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e ".[test]"
pytest
```

Run the demo with `pip install -e ".[demo]"` and `python examples/flask_demo.py <file>`.

**Suggested contributor checks:** `pytest`, plus a linter and type checker of your choice (for example `ruff` and `mypy`) before opening a pull request.

## Production Checklist

Before exposing UniversalDRM to real users:

- [ ] Originals live in **private storage**; no public URL or bucket exists for them
- [ ] Every page/video route **authenticates and authorizes** the viewer
- [ ] Sessions are **bound to a verified identity** and expire quickly
- [ ] `Cache-Control: no-store` is set on all content responses
- [ ] `statusUrl` reflects **revocation and expiry** in real time
- [ ] **Per-session rate limits** on page requests are in place
- [ ] Watermark text includes **identity, short session id, timestamp**
- [ ] **HTTPS** everywhere; HSTS enabled
- [ ] Strict **CSP** and security headers configured
- [ ] Uploads are **validated** (magic bytes, size) and scanned; rendering runs in a **resource-limited, sandboxed** process for untrusted files
- [ ] Logs capture page requests and status failures
- [ ] Your product copy says "**capture-resistant / traceable**", not "screenshot-proof"

> **Untrusted files:** PDF and image parsers are attack surface. Render untrusted uploads in an isolated worker with CPU, memory and time limits, a non-root user, and no network access.

## Project Status

**Alpha (v0.1.x).** The core rendering library and browser viewer are functional and used in production by [ForceX](https://github.com/eklavya2201/ForceX). The public API may change between minor versions until 1.0. Pin your dependency to a tag.

| Component | State |
|---|---|
| PDF / image / text rendering | Available |
| Burned-in watermark | Available |
| Canvas viewer + deterrence layer | Available |
| Video streaming with overlay watermark | Available |
| Status polling / live revocation | Available |
| Forensic (invisible) watermark | Planned |
| Identity-bound shares, OTP, sessions | Planned |
| Office document support | Planned |
| Multi-DRM media | Planned |

## Roadmap

| Milestone | Focus |
|---|---|
| **v0.1** | PDF, image, text and video viewing; burned-in watermark; canvas viewer; deterrence; live status |
| **v0.2** | Tile-based delivery; per-session page-rate limiting helpers; accessibility mode; TypeScript helper package |
| **v0.3** | Forensic (invisible) watermarking with a trace utility; optional identity-bound share and OTP reference implementation |
| **v0.4** | DOCX/PPTX via sandboxed conversion; conversion preview |
| **v0.5** | Encrypted file storage providers; envelope encryption and key-provider interface |
| **v0.6** | Media: CMAF/CBCS packaging, vendor-backed Widevine/PlayReady/FairPlay adapters |
| **v1.0** | Stable API, audit and policy interfaces, hardened reference deployment, third-party security review |

Design details and open questions live in [`docs/implementation_plan.md`](docs/implementation_plan.md). Roadmap items are plans, not commitments.

## Security Policy

Please **do not** open public issues for security vulnerabilities.

Report privately through [GitHub Security Advisories](https://github.com/neelmali182/UniversalDRM/security/advisories/new). Include reproduction steps, affected version, and impact. You can expect an acknowledgment and a coordinated fix and disclosure process.

If you add a `SECURITY.md` to the repository, GitHub will surface it on the Security tab automatically.

**Scope notes:** reports that amount to "a screenshot or camera captured the screen" or "DevTools can disable the blur" are known, documented limitations (see [What it cannot protect against](#what-it-cannot-protect-against)). Reports of *enforced* properties failing (for example an endpoint exposing an original, or a watermark that can be stripped from server output) are in scope and welcome.

## Contributing

Contributions are welcome.

1. **Discuss first** for non-trivial changes: open an issue describing the problem and proposed approach.
2. **Fork** the repository and create a feature branch: `git checkout -b feat/short-description`.
3. **Write tests** for new behavior and keep existing tests green (`pytest`).
4. **Keep security claims honest.** Any new protection must be labelled *enforced*, *best-effort*, or *traceability* in code comments and docs.
5. **Commit clearly** (Conventional Commits such as `feat:`, `fix:`, `docs:` are encouraged) and open a pull request with a description of the change, motivation, and test evidence.

**Good first areas:** additional test fixtures (malformed PDFs, huge images), watermark layout options, accessibility mode, documentation and framework integration examples (FastAPI, Django).

## FAQ

**Is this "DRM"?**
Not in the Widevine/FairPlay sense. It is content protection and capture resistance: server-side rendering, burned-in watermarks, and deterrence. The name reflects the goal, not a claim of hardware-backed DRM.

**Can it stop screenshots?**
No. No website can. It makes each capture traceable to the viewer through the watermark and discourages casual extraction. For hard capture blocking, use a native app with OS capture exclusion.

**Why render pages as images instead of using PDF.js?**
PDF.js requires sending the whole PDF to the browser. Server-side rasterization means the client never has the file, and the watermark can be burned into pixels.

**Does it support accessibility (screen readers)?**
Not yet. Canvas rendering removes the text layer by design. An opt-in, watermarked accessible mode is on the roadmap.

**Does it handle authentication or sharing links?**
No. It is the rendering and viewing layer. See the [Integration Guide](#integration-guide) for what your application must provide.

**Is video protected as strongly as documents?**
No. The video file is streamed and the watermark is an overlay. See [What it cannot protect against](#what-it-cannot-protect-against).

**Can I use it commercially?**
Yes. It is MIT licensed. Note that dependencies carry their own licenses; review them for your use case.

## License

Released under the [MIT License](LICENSE).

---

<div align="center">

**UniversalDRM: technically achievable security over exaggerated claims.**

</div>