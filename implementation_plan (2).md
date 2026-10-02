# ForceX × UniversalDRM — Detailed Implementation Plan

> **ForceX** is the product and the app (web sender console + Windows app + Android app).
> **UniversalDRM** is the DRM rendering library that ForceX uses to show documents without handing over the file.
>
> Plan date: 2026-10-01

---

## Table of Contents

1. [About the Project](#1-about-the-project)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [Who Does What: ForceX vs UniversalDRM](#3-who-does-what-forcex-vs-universaldrm)
4. [Tech Stack](#4-tech-stack)
5. [Architecture](#5-architecture)
6. [Protection Modes](#6-protection-modes)
7. [Audit Log](#7-audit-log)
8. [Sender Side (ForceX Web)](#8-sender-side-forcex-web)
9. [Receiver Flow](#9-receiver-flow)
10. [Windows App](#10-windows-app)
11. [Android App](#11-android-app)
12. [UniversalDRM Changes](#12-universaldrm-changes)
13. [Security Model](#13-security-model)
14. [Configuration](#14-configuration)
15. [Build, CI and Distribution](#15-build-ci-and-distribution)
16. [Testing Plan](#16-testing-plan)
17. [Roadmap](#17-roadmap)
18. [File-by-File Change Map](#18-file-by-file-change-map)
19. [Open Questions](#19-open-questions)

---

## 1. About the Project

ForceX is a private, one-time file-sharing product. A sender uploads a file on the web and creates a temporary share link. The receiver opens the link and either views the file or downloads it once, depending on what the sender chose.

The sender also chooses how strongly the file is protected while it is being viewed:

- **Any browser:** the receiver opens the link in a normal browser. UniversalDRM renders the file as page images drawn on canvases, with the watermark burned in. No file is sent, so there is nothing to save, copy or print.
- **ForceX app only:** the receiver must open the link in the ForceX app (Windows or Android). The app tells the operating system to exclude its window from screenshots and screen recording, and it blocks downloads and printing. No watermark is drawn in this mode, because the OS already blocks capture.

Every open is recorded in an audit log, in both modes.

### 1.1 Current state

| Area | State |
|---|---|
| Sender web UI (upload, create share, revoke) | Done |
| Receiver web viewer (UniversalDRM canvas, status polling, revocation) | Done |
| View-once mode | Done |
| Download-once mode | Done |
| Protection = browser | Done |
| Protection = app (header check, `X-ForceX-Client`) | Done |
| Windows app (PySide6 + QtWebEngine, `WDA_EXCLUDEFROMCAPTURE`) | Done (basic) |
| Android app | Not started |
| Sender UI for choosing protection and platform | Partial |
| Audit log | Exists (`backend/audit.py`); needs app-mode fields |

### 1.2 What this plan adds

1. Android app (Kotlin, `FLAG_SECURE`).
2. Sender form for choosing the protection level and platform.
3. Receiver landing page with per-platform download instructions.
4. Watermark rules: on in browser mode, off in app mode.
5. Audit log kept in app mode, with client type, app version and device recorded.
6. Windows app hardening (focus-loss blanking, Qt-level shortcut blocking, branding, CI build).
7. UniversalDRM improvements (optional watermark, always-on watermark option, session end on `getDisplayMedia`, clipboard clear).

---

## 2. Goals and Non-Goals

### Goals
- Receivers can view a file without ever receiving the file itself.
- In app mode, screenshots and screen recording are blocked by the operating system.
- Senders can revoke a share at any time and the open viewer is wiped.
- Every open is logged with enough detail to give the sender a trail.
- One server, one rendering path: the apps are thin hardened shells around the same web viewer.

### Non-Goals
- Stopping a phone camera pointed at a screen.
- Replacing Widevine/PlayReady/FairPlay-class DRM. UniversalDRM is not that, and the docs say so.
- macOS, iOS and Linux apps in v1.
- Watermarking in app mode.

---

## 3. Who Does What: ForceX vs UniversalDRM

| | ForceX | UniversalDRM |
|---|---|---|
| What it is | The product and app: web console, Windows app, Android app, server | The DRM library ForceX uses for rendering |
| Repo | `eklavya2201/ForceX` | `neelmali182/UniversalDRM` |
| Owns | Accounts, shares, tokens, sessions, expiry, revocation, audit log, storage, protection modes, native apps | Turning PDFs/images/text into page images, burning watermarks into pixels, canvas viewer JS, deterrence layer (key blocking, blur on focus loss), status polling |
| Does not own | How pages are rendered | Who is allowed to view, sessions, storage, anything about apps |
| Interface | Calls `renderer.render_page(...)` and mounts `UniversalDRM.mount(...)` | Python `Renderer` + `static/universal-drm.js` |
| Install in ForceX | Pinned as a dependency (`pip install ... @ git+https://github.com/neelmali182/UniversalDRM@vX.Y.Z`) | Tagged releases |

Rule of thumb: **ForceX decides, UniversalDRM draws.** ForceX tells UniversalDRM what text to burn in (or none), and UniversalDRM returns the image.

---

## 4. Tech Stack

### 4.1 ForceX server and web

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | Flask (application factory in `backend/__init__.py`) |
| WSGI server | Waitress (`run.py`); `wsgi.py` for PythonAnywhere-style hosts |
| Database | SQLAlchemy; SQLite locally, Postgres (Neon) in production |
| Auth | Flask-Login; Argon2 password hashing |
| Security | CSRF protection, rate limiting, security headers (`backend/extensions.py`, `backend/__init__.py`) |
| Storage | Local private directory (`FORCEX_STORAGE`) or Vercel Blob (when `BLOB_READ_WRITE_TOKEN` is set) |
| Templates | Jinja (`templates/`) |
| Front-end | Plain JS (`static/viewer.js`), CSS |
| Hosting | Vercel (Neon + Blob), PythonAnywhere, or Render (see `DEPLOY.md`) |

### 4.2 UniversalDRM

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Rendering | pypdfium2 (PDF → image), Pillow (images, text pages, watermark, JPEG encode) |
| Browser side | Dependency-free JavaScript (`universal-drm.js`) and CSS; works under strict CSP |
| Tests | pytest |

### 4.3 Windows app

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| UI | PySide6 + QtWebEngine (`QWebEngineView`) |
| Capture protection | `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE = 0x11)` via `ctypes` (Windows 10 2004+) |
| Packaging | PyInstaller via `build_desktop.py` → `dist/ForceX.exe` |
| Signing | Authenticode certificate (decision pending, see §19) |

### 4.4 Android app

| Layer | Technology |
|---|---|
| Language | Kotlin |
| UI | Native Android `WebView` inside a single `Activity` |
| Capture protection | `WindowManager.LayoutParams.FLAG_SECURE` |
| Build | Gradle (`assembleRelease`), signed with a keystore |
| Min SDK | Decide at project creation (see §19); `FLAG_SECURE` itself works on all supported versions |
| Distribution | Direct APK download (sideload) for v1 |

### 4.5 Why Kotlin for Android

| Option | Verdict |
|---|---|
| Python (Buildozer + Kivy) | Not recommended. WebView integration is limited, `FLAG_SECURE` is awkward, APK is large. |
| Kotlin (native) | **Chosen.** Full control, `FLAG_SECURE` is one call, WebView fully supported, small APK. |
| React Native / Flutter | Possible, but WebView security features are less direct. Kept as a fallback only. |

### 4.6 CI

GitHub Actions: one workflow to build the Windows EXE, one to build and sign the Android APK, both publishing to GitHub Releases.

---

## 5. Architecture

### 5.1 System overview

```
                      ┌─────────────────────────────────────────────┐
                      │               FORCEX SERVER (Flask)          │
                      │                                             │
                      │  auth.py      shares.py     receive.py      │
                      │  tokens.py    storage.py    cleanup.py      │
                      │  audit.py     models.py     extensions.py   │
                      │                                             │
                      │      ┌───────────────────────────────┐      │
                      │      │  UniversalDRM (Python lib)    │      │
                      │      │  Renderer.render_page()       │      │
                      │      └───────────────────────────────┘      │
                      └───────────────┬─────────────────────────────┘
                                      │ HTTPS
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐            ┌────────────────┐            ┌─────────────────┐
│  Sender       │            │  Any browser   │            │  ForceX apps    │
│  (web console)│            │  (receiver)    │            │  (receiver)     │
│               │            │                │            │                 │
│  upload,      │            │  UniversalDRM  │            │  Windows EXE    │
│  create share,│            │  JS canvas     │            │  Android APK    │
│  revoke, view │            │  viewer +      │            │  = hardened     │
│  audit log    │            │  watermark     │            │  WebView shell  │
└───────────────┘            └────────────────┘            │  + OS capture   │
                                                           │  blocking       │
                                                           │  + UniversalDRM │
                                                           │  JS viewer      │
                                                           │  (no watermark) │
                                                           └─────────────────┘
```

The server does not have a separate rendering path for apps. The apps load the same receiver pages and the same UniversalDRM viewer. The differences are:

1. The app sends `X-ForceX-Client` (and platform/version headers) so the server knows it is the app.
2. The app asks the OS to exclude its window from capture.
3. The app blocks downloads, printing and external navigation.
4. For app-mode shares the server renders pages **without** a watermark.

### 5.2 Components

| Component | Responsibility |
|---|---|
| `backend/auth.py` | Sender registration, login, logout |
| `backend/shares.py` | Create share (mode + protection + platform), dashboard, revoke |
| `backend/receive.py` | Receiver landing, open action, viewer, page images, status, end, download; the app-only gate (`desktop_only()` hook) |
| `backend/tokens.py` | Share token hashing, atomic consumption, receiver sessions |
| `backend/storage.py` | Upload handling, local or Blob storage, archives |
| `backend/cleanup.py` | Expiry sweeps and scheduler |
| `backend/audit.py` | Access and security event logging |
| `backend/models.py` | Users, shares, files, sessions, audit records |
| `browser/forcex_browser.py` | Windows app |
| `android/` | Android app |
| `universal_drm/` | Renderer, static JS/CSS |

### 5.3 Data model changes

`Share.protection` currently holds `"browser"` or `"app"`.

New allowed values:

| Value | Meaning |
|---|---|
| `browser` | Any browser, UniversalDRM viewer with watermark |
| `app_windows` | ForceX Windows app only |
| `app_android` | ForceX Android app only |
| `app_any` | Either ForceX app |

Existing rows with `"app"` are migrated to `"app_windows"` (that is what the old value implied).

Audit records gain the fields listed in §7.

### 5.4 Receiver request flow

```
Receiver clicks link  →  GET /s/<token>
                              │
                    desktop_only() hook runs
                              │
        ┌─────────────────────┴──────────────────────┐
        │ protection = browser                        │ protection = app_*
        │ → continue                                  │ → check X-ForceX-Client
        │                                             │
        │                                  ┌──────────┴───────────┐
        │                                  │ header valid         │ header missing/invalid
        │                                  │ → continue           │ → 403 page: "Requires the
        │                                  │                      │   ForceX app" + download
        │                                  │                      │   button for the platform
        ▼                                  ▼                      │   (audit: blocked attempt)
   Landing page (does NOT consume the share)
        │  optional passcode
        ▼
   POST /s/<token>/open   → atomically consume token → create receiver session
        │
        ▼
   GET /v/<share_id>           viewer page
   GET /v/<share_id>/file      page images (UniversalDRM) or video
   GET /v/<share_id>/status    polled by viewer; {"active": true} or session ends
   POST /v/<share_id>/end      ends the session
   GET /v/<share_id>/download  download-once only
```

### 5.5 Rendering rules by protection

| Protection | Watermark on page images | Watermark overlay on video | Always-on watermark option |
|---|---|---|---|
| `browser` | Yes (share label, share ID, viewer network, open time) | Yes | `alwaysWatermark: true` |
| `app_windows` / `app_android` / `app_any` | **No** | **No** | Not used |

---

## 6. Protection Modes

The sender picks a **share mode** first, then a **protection level** for view-once.

### 6.1 Share modes

| Mode | Behaviour |
|---|---|
| View once | Receiver can view, cannot download. Session limited by `FORCEX_VIEW_TTL_MIN`. |
| Download once | Receiver gets one real file download, then the share is consumed. Always works in a normal browser (the receiver gets the file anyway). |

### 6.2 Protection levels (view once only)

**Mode 1: Any browser**
- UniversalDRM canvas viewer.
- Watermark burned into the pixels.
- Key blocking, context menu and drag blocked, blur/blackout on focus loss.
- Live revocation via status polling.
- Best-effort deterrence only; an OS screenshot is not blockable from a web page.

**Mode 2: ForceX app, Windows**
- Receiver must open `ForceX.exe`.
- `WDA_EXCLUDEFROMCAPTURE`: the window is left out of screenshots, the Snipping Tool, recorders and screen sharing.
- Downloads, printing and the context menu blocked at app level.
- Server gate: `X-ForceX-Client` required.
- No watermark.

**Mode 3: ForceX app, Android**
- Receiver must open the ForceX APK.
- `FLAG_SECURE`: window is black in screenshots, recordings, casting and screen sharing.
- WebView with download, share and external navigation blocked.
- Server gate: `X-ForceX-Client` required.
- No watermark.

**Mode 2+3 combined (`app_any`)**: either app is accepted.

---

## 7. Audit Log

The audit log is kept in **all** modes, including app mode. It costs nothing on screen and gives the sender a trail if something leaks.

### 7.1 Events recorded

| Event | When |
|---|---|
| `share_created` | Sender creates a share |
| `landing_viewed` | Receiver loads `/s/<token>` (does not consume) |
| `gate_blocked` | App-only share requested without a valid client header |
| `passcode_failed` | Wrong passcode |
| `opened` | Receiver submits the open action; share consumed |
| `page_served` | A page image is served (optional, may be sampled) |
| `status_ended` | Session ended by status poll (revoked/expired) |
| `session_ended` | Receiver or viewer ended the session |
| `downloaded` | Download-once file served |
| `revoked` | Sender revokes |
| `expired` | Share expires |

### 7.2 Fields per record

| Field | Source |
|---|---|
| `share_id` | Share |
| `event` | Event name above |
| `timestamp` (UTC) | Server |
| `ip` | Request (correct behind proxy when `FORCEX_BEHIND_PROXY=1`) |
| `user_agent` | Request header |
| `client_type` | `browser` / `windows_app` / `android_app` |
| `app_version` | `X-ForceX-App-Version` header (apps only) |
| `platform` | `X-ForceX-Platform` header (`windows` / `android`), else derived from User-Agent |
| `device` | Short summary built from User-Agent and platform header |
| `detail` | Free text / JSON for the event (e.g. failure reason) |

### 7.3 Sender view
The dashboard shows, per share: protection level, status, and an expandable list of audit events (time, event, IP, client type, device).

---

## 8. Sender Side (ForceX Web)

### 8.1 New share form (`templates/sender/new.html`)

```
Share mode:
  ( ) View once       → receiver can view, cannot download
  ( ) Download once   → receiver gets one real file download

[Shown only for "View once"]
Protection:
  ( ) Any browser
        Anyone with the link can view. Capture is deterred, not blocked.
        A watermark is burned into the pages.
  ( ) ForceX App only
        Receiver must open the ForceX app. Screen capture is blocked by
        the operating system. No watermark is drawn.
        Platform:  ( ) Windows   ( ) Android   ( ) Either
```

### 8.2 Backend (`backend/shares.py`)

```python
# Previously (line ~63):
# protection = "app" if mode == "view" and request.form.get("protection") == "app" else "browser"

if mode == "view":
    plat = request.form.get("platform", "")          # windows / android / any
    if request.form.get("protection") == "app":
        protection = {"windows": "app_windows", "android": "app_android"}.get(plat, "app_any")
    else:
        protection = "browser"
else:
    protection = "browser"   # download-once always gives the real file
```

### 8.3 Other sender-side changes
- `dashboard.html`: add a **Protection** column (Browser / Windows app / Android app / Any app).
- `created.html`: when protection is an app mode, show the matching download link(s) so the sender can pass them to the receiver.
- Dashboard: "Download ForceX for Windows" and "Download ForceX for Android" buttons.

---

## 9. Receiver Flow

### 9.1 Browser receiver (protection = `browser`)
1. Open link → landing page → optional passcode → open.
2. UniversalDRM viewer mounts with `alwaysWatermark: true`.
3. Pages load as watermarked JPEGs, drawn on canvases.
4. Viewer polls `/status`; if the share is revoked or the session expires, content is wiped.

### 9.2 App receiver (protection = `app_*`)
1. Receiver installs the ForceX app (download links are on the sender's `created.html` and the receiver's gate page).
2. Receiver opens the share link in the app (paste into the bar, or pass as an argument on Windows).
3. App sends `X-ForceX-Client` (plus platform and version) on every request; the server passes the gate.
4. Viewer mounts **without** a watermark. The OS blocks capture.
5. Status polling and revocation behave the same as in the browser.

### 9.3 Browser opening an app-only link
The server returns 403 with `receiver/desktop_only.html`:
- Windows share: "Download ForceX.exe" button.
- Android share: "Download ForceX.apk" button with sideload instructions.
- Either: both.

The attempt is recorded as `gate_blocked`.

### 9.4 Gate code (`backend/receive.py`)

```python
APP_PROTECTIONS = ("app", "app_windows", "app_android", "app_any")  # "app" kept for legacy rows

def desktop_only():
    share = current_share()
    if share is None or share.protection not in APP_PROTECTIONS:
        return None

    sent = request.headers.get("X-ForceX-Client", "")
    if hmac.compare_digest(sent.encode(), current_app.config["CLIENT_KEY"].encode()):
        return None

    audit.log("gate_blocked", share_id=share.id)
    if share.protection == "app_android":
        platform = "android"
    elif share.protection == "app_any":
        platform = "any"
    else:
        platform = "windows"
    return render_template("receiver/desktop_only.html", platform=platform), 403
```

### 9.5 Per-page rendering (`backend/receive.py`)

```python
if share.protection == "browser":
    watermark_text = viewer_watermark(share, vs) + f" · p{index}"
else:
    watermark_text = None            # app mode: no watermark

data = renderer.render_page(local_path(current_app, f), f.mime, index, watermark_text)
```

---

## 10. Windows App

### 10.1 What exists
- `browser/forcex_browser.py`: PySide6 + `QWebEngineView`.
- `WDA_EXCLUDEFROMCAPTURE = 0x11` through `ctypes`.
- `ClientKeyInterceptor` adds `X-ForceX-Client`.
- `LockedPage` blocks navigation to non-ForceX URLs.
- Downloads blocked, printing blocked, context menu disabled.
- `build_desktop.py` → PyInstaller → `dist/ForceX.exe`.

### 10.2 Improvements

**10.2.1 Refuse to run without capture protection.** If `SetWindowDisplayAffinity` fails (e.g. Windows older than 10 2004), show a message box and exit. Do not fall back to an unprotected mode.

**10.2.2 Blank on focus loss.** When the window loses focus (Alt+Tab, Win+D), hide the web view and show a dark screen; restore when focus returns.

```python
def changeEvent(self, event):
    if event.type() == QEvent.Type.WindowDeactivate:
        self.view.setHidden(True)
    elif event.type() == QEvent.Type.WindowActivate:
        self.view.setHidden(False)
```

**10.2.3 Qt-level shortcut blocking.** Block PrintScreen, Ctrl+P, Ctrl+S and Ctrl+C at the Qt layer, in addition to the JS blocking inside the viewer.

**10.2.4 Headers.** Send `X-ForceX-Client`, `X-ForceX-Platform: windows` and `X-ForceX-App-Version` on every request (extend `ClientKeyInterceptor`).

**10.2.5 Branding.** Proper application icon and window title.

**10.2.6 Client key handling.** The key is baked in at build time (`--url`, `--key`). A `forcex.env` next to the EXE overrides the baked values. When the server key rotates, the EXE must be rebuilt, or the EXE fetches the key at runtime from a `/client-config` endpoint gated by a setup code (decision in §19).

**10.2.7 Distribution.** The sender dashboard and the receiver gate page link to the GitHub Release (`FORCEX_DESKTOP_DOWNLOAD_URL`). The EXE should be code-signed to avoid SmartScreen warnings.

---

## 11. Android App

### 11.1 Why it is separate
No PySide6 and no QtWebEngine on Android. The app uses Android's own `WebView`, and `FLAG_SECURE` is the Android equivalent of `WDA_EXCLUDEFROMCAPTURE`.

### 11.2 Project structure

```
ForceX/
└── android/
    ├── app/
    │   ├── build.gradle
    │   ├── proguard-rules.pro
    │   └── src/main/
    │       ├── AndroidManifest.xml
    │       ├── java/com/forcex/app/
    │       │   ├── MainActivity.kt           # window, FLAG_SECURE, WebView, focus handling
    │       │   ├── ForceXWebViewClient.kt    # headers, navigation lock
    │       │   ├── ForceXWebChromeClient.kt  # blocks file chooser, camera, popups
    │       │   └── Config.kt                 # baked-in FORCEX_URL + CLIENT_KEY
    │       └── res/
    │           ├── layout/activity_main.xml
    │           └── values/strings.xml
    ├── build.gradle
    └── settings.gradle
```

### 11.3 `FLAG_SECURE`

```kotlin
// MainActivity.kt — in onCreate, BEFORE setContentView
window.setFlags(
    WindowManager.LayoutParams.FLAG_SECURE,
    WindowManager.LayoutParams.FLAG_SECURE
)
```

Effect: black in screenshots, screen recorders, casting and screen sharing, assistant screen context, and the recent-apps thumbnail.

### 11.4 WebView settings

```kotlin
webView.settings.apply {
    javaScriptEnabled = true          // required by the UniversalDRM viewer
    domStorageEnabled = false
    databaseEnabled = false
    allowFileAccess = false
    allowContentAccess = false
    setSupportZoom(false)
    builtInZoomControls = false
    displayZoomControls = false
    mediaPlaybackRequiresUserGesture = false
}
webView.isLongClickable = false
webView.setOnLongClickListener { true }
webView.isHapticFeedbackEnabled = false
```

If the viewer turns out to need `domStorageEnabled`, enable it and re-test (see §16).

### 11.5 Headers (`X-ForceX-Client`)
Every request from the app to the ForceX host must carry:

| Header | Value |
|---|---|
| `X-ForceX-Client` | Baked-in client key |
| `X-ForceX-Platform` | `android` |
| `X-ForceX-App-Version` | `BuildConfig.VERSION_NAME` |

Implementation requirement: the header must reach **all** requests, including the `POST /s/<token>/open` form submission and the page-image requests. Note that `shouldInterceptRequest` does not expose request bodies, so re-fetching requests there will break POST forms. During implementation, pick a mechanism that reaches every request without re-fetching (for example, a cookie set through `CookieManager`, or a User-Agent suffix the server also accepts), and have the server's gate accept it. Verify with the form-post and image requests in §16.

```kotlin
class ForceXWebViewClient(private val serverHost: String) : WebViewClient() {

    // Block navigation to any other host
    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        return request.url.host != serverHost
    }
}
```

### 11.6 Block downloads, popups and pickers

```kotlin
webView.setDownloadListener { _, _, _, _, _ ->
    Toast.makeText(this, "Downloads are not permitted in ForceX.", Toast.LENGTH_SHORT).show()
}
```

`ForceXWebChromeClient` overrides `onShowFileChooser` (return false/cancel), `onCreateWindow` (return false), and denies camera/microphone/geolocation permission requests.

### 11.7 Focus-loss blanking

```kotlin
override fun onWindowFocusChanged(hasFocus: Boolean) {
    super.onWindowFocusChanged(hasFocus)
    webView.visibility = if (hasFocus) View.VISIBLE else View.INVISIBLE
}
```

Also hide the content in `onPause` / `onStop` and restore on `onResume`.

### 11.8 Opening a share
- Share link can be pasted into the app's address bar, or opened with an intent if a link handler is added later.
- The app loads only `Config.FORCEX_URL` and paths under it.

### 11.9 Config baking
`Config.kt` is generated by a build script from environment variables:

```kotlin
object Config {
    const val FORCEX_URL = "https://your-forcex-site"
    const val CLIENT_KEY = "..."   // injected at build time, never committed
}
```

v1: build-time baking (same as the EXE). v2: first-launch setup code that decodes URL + key.

### 11.10 Build and distribution
- `./gradlew assembleRelease` → `app-release.apk`, signed with a keystore stored in CI secrets.
- v1: direct APK download from GitHub Releases, with sideload instructions on the gate page.
- Play Store: later, if needed (policy review required).

---

## 12. UniversalDRM Changes

All in the UniversalDRM repo. ForceX picks them up by bumping the pinned tag.

### 12.1 Optional watermark (needed for app mode)
`Renderer.render_page(path, mime, index, watermark_text)` must accept `None` (or empty string) and then **skip** drawing the watermark. Verify the current behaviour first; add the option if it is not already supported. Same for the video overlay: `UniversalDRM.mount(...)` with no `watermark` option draws no overlay.

### 12.2 `alwaysWatermark` mount option (browser mode)
In `universal-drm.js`, add `alwaysWatermark`:
- `false` (default): the watermark layer is drawn only on detected capture signals.
- `true`: the watermark layer is always drawn.

ForceX passes `alwaysWatermark: true` for browser-mode shares only. For app-mode shares it passes no watermark at all.

Before implementing, check whether the pixel-burned watermark on page images already covers this for documents, in which case `alwaysWatermark` matters mainly for the video overlay.

### 12.3 End the session on `getDisplayMedia`

```javascript
navigator.mediaDevices.getDisplayMedia = async function (...args) {
    setCaptureMode(true, 15000);
    if (o.endOnCapture && o.statusUrl) {
        fetch(o.statusUrl.replace('/status', '/end'), {
            method: 'POST', credentials: 'same-origin'
        }).catch(() => {});
    }
    end('capture-detected');
    return origGetDisplayMedia(...args);
};
```

### 12.4 Clear the clipboard on copy/cut

```javascript
['copy', 'cut'].forEach(type => on(document, type, e => {
    e.preventDefault();
    if (navigator.clipboard) navigator.clipboard.writeText('').catch(() => {});
}));
```

### 12.5 Later (separate repo roadmap)
Tile-based page delivery (v0.2), per-session rate-limit helpers (v0.2), forensic/invisible watermark (v0.3).

---

## 13. Security Model

| Attack | Browser (any) | ForceX Windows app | ForceX Android app |
|---|---|---|---|
| Right-click save image | Blocked (canvas) | Blocked (canvas + no context menu) | Blocked (canvas + long-click disabled) |
| Copy text | Blocked (no text layer) | Blocked | Blocked |
| Ctrl+S / download | Blocked (route check) | Blocked (Qt download block) | Blocked (WebView download listener) |
| Ctrl+P / print | Blocked (keydown) | Blocked (Qt print block) | Blocked (no print path) |
| DevTools | Deterred (key block) | No DevTools unless debug flag is set | No DevTools |
| Network-tab scrape | Hard (no original URL) | Hard | Hard |
| PrintScreen | Content blurs, clipboard cleared where allowed | **Window excluded from capture** | **Window black (`FLAG_SECURE`)** |
| Win+Shift+S / Snipping Tool | Blur heuristic only | **Window excluded** | n/a |
| Android screenshot | n/a | n/a | **Black (`FLAG_SECURE`)** |
| Screen recorder (OBS etc.) | Not detectable | **Window excluded** | **Black** |
| Screen sharing (Teams/Zoom/Meet) | Not blockable | **Window excluded** | **Excluded** |
| Phone camera at screen | Not blockable (watermarked) | Not blockable | Not blockable |
| ADB screencap | n/a | n/a | Black |
| Link forwarding / reuse | One-time token enforced | Enforced | Enforced |
| Bulk page scraping with valid session | Rate limited | Rate limited | Rate limited |
| Access after revocation | Wiped on next status poll | Wiped | Wiped |
| Watermark | Yes | No | No |
| Audit log entry | Yes | Yes | Yes |

### 13.1 Honest limits (state these in the product docs)
- This is not hardware DRM.
- The client key ships inside the app, so a determined user can extract it and fetch content with a script. In app mode that content is **not watermarked**. Mitigations in this plan: one-time tokens, short session TTL, rate limiting, audit log.
- Nothing stops a camera pointed at the screen.

---

## 14. Configuration

| Variable | Default | Description |
|---|---|---|
| `FORCEX_SECRET_KEY` | none | Required. Flask secret. |
| `FORCEX_CLIENT_KEY` | none | Required. Shared with the apps; app-only receiver routes refuse requests without it. |
| `FORCEX_DB` | `sqlite:///forcex.db` | SQLAlchemy URL. `DATABASE_URL` (Postgres) used when unset. |
| `FORCEX_STORAGE` | `<project>/storage` | Private blob storage directory. |
| `FORCEX_MAX_UPLOAD_MB` | `500` | Max upload size. |
| `FORCEX_VIEW_TTL_MIN` | `10` | View session lifetime. |
| `FORCEX_DOWNLOAD_TTL_MIN` | `5` | Download session lifetime. |
| `FORCEX_COOKIE_SECURE` | `0` | Set `1` on HTTPS. |
| `FORCEX_ALLOW_REGISTRATION` | `1` | Set `0` to close sender signup. |
| `FORCEX_BEHIND_PROXY` | `0` | Set `1` behind a reverse proxy. |
| `FORCEX_SCHEDULER` | `1` | Set `0` on hosts without background threads. |
| `FORCEX_DESKTOP_DOWNLOAD_URL` | repo latest release | Windows download button target. |
| `FORCEX_ANDROID_DOWNLOAD_URL` | **new**, repo latest release | Android download button target. |
| `BLOB_READ_WRITE_TOKEN` | none | Use Vercel Blob storage when set. |

---

## 15. Build, CI and Distribution

### 15.1 Windows (`.github/workflows/build_exe.yml`)
1. Check out, set up Python 3.12, install `requirements-desktop.txt` and PyInstaller.
2. Run `python build_desktop.py --url $FORCEX_URL --key $FORCEX_CLIENT_KEY`.
3. Sign `dist/ForceX.exe` (when a certificate is available).
4. Upload `ForceX.exe` to GitHub Releases.

### 15.2 Android (`.github/workflows/build_apk.yml`)
1. Check out, set up JDK and Android SDK.
2. Generate `Config.kt` from `FORCEX_URL` and `FORCEX_CLIENT_KEY` secrets.
3. `./gradlew assembleRelease`.
4. Sign with the keystore from CI secrets.
5. Upload `ForceX.apk` to GitHub Releases.

### 15.3 Server
Unchanged: Vercel (Neon + Blob), PythonAnywhere, or Render per `DEPLOY.md`. Bump the UniversalDRM pin in `requirements.txt` when UniversalDRM releases a new tag.

### 15.4 Secrets
`FORCEX_CLIENT_KEY`, the Android keystore and its passwords, and (later) the Authenticode certificate live in CI secrets only. They are never committed.

---

## 16. Testing Plan

ForceX has no automated test suite today. Add tests at least for the access-control changes.

### 16.1 Server (pytest)
- Gate: `browser` share opens without header; `app_*` share returns 403 without header and 200 with a valid header; wrong key is rejected; comparison is constant-time.
- Legacy `"app"` rows still gate correctly after migration.
- Platform-specific 403 page content for `app_windows`, `app_android`, `app_any`.
- Share creation maps form values to the right `protection`.
- Rendering: `browser` share passes watermark text; `app_*` share passes none.
- Audit: each event in §7 writes a record with the expected fields, including `client_type` and `app_version` from headers.
- Token consumption is atomic; revoked and expired shares are refused.

### 16.2 UniversalDRM (pytest)
- `render_page` with `None` watermark returns a valid JPEG with no watermark drawn.
- `render_page` with text still burns it in.

### 16.3 Windows app (manual)
- Window is black/absent in Snipping Tool, Win+Shift+S, OBS, Teams/Zoom share.
- App refuses to start where capture exclusion is unavailable.
- Focus loss blanks content and restores on return.
- Download, print and context menu blocked; navigation to other hosts blocked.
- Share opens end to end, including the passcode form POST.

### 16.4 Android app (manual, real device)
- Screenshot, screen recording, casting and recent-apps thumbnail are black.
- ADB `screencap` is black.
- Open form POST works with the header mechanism chosen in §11.5.
- Page images load (header reaches subresources).
- Downloads, long-press, file chooser and popups blocked.
- Navigation to other hosts blocked.
- Content hidden on pause/focus loss.

### 16.5 Browser (manual)
- Watermark visible on every page; key blocking works; blur on focus loss; revocation wipes the viewer.

---

## 17. Roadmap

### Phase 0 — Foundation (done)
Flask app, view-once, download-once, browser protection, UniversalDRM canvas viewer, basic Windows app.

### Phase 1 — Quick wins (1–2 weeks)

| Task | Files | Effort |
|---|---|---|
| UniversalDRM: accept no watermark | `universal_drm/render.py`, `universal-drm.js` | 2h |
| UniversalDRM: `alwaysWatermark` option | `universal-drm.js` | 1h |
| ForceX: pass `alwaysWatermark: true` for browser shares only | `viewer.js`, `viewer.html` | 30m |
| ForceX: no watermark for app-mode shares | `receive.py` | 30m |
| End session on `getDisplayMedia` | `universal-drm.js` | 1h |
| Clipboard clear on copy/cut | `universal-drm.js` | 30m |
| Per-page watermark text (browser shares) | `receive.py` | 30m |
| Windows: focus-loss blanking | `forcex_browser.py` | 1h |
| Audit log: add client type, app version, platform, device fields | `audit.py`, `models.py` | 3h |

### Phase 2 — Sender mode selection (2–3 weeks)

| Task | Files | Effort |
|---|---|---|
| New share form: platform choice | `new.html`, `shares.py` | 1 day |
| New `protection` values + migration of `"app"` rows | `models.py`, `shares.py`, `receive.py` | 3h |
| Gate hook handles new values | `receive.py` | 1h |
| Platform-specific gate page | `desktop_only.html` | 2h |
| Dashboard protection column + audit view | `dashboard.html` | 3h |
| Server tests for gate, creation, rendering, audit | `tests/` | 1–2 days |

### Phase 3 — Android app (4–6 weeks)

| Task | Files | Effort |
|---|---|---|
| Create Gradle/Kotlin project | `android/` | 1 day |
| `FLAG_SECURE` | `MainActivity.kt` | 2h |
| WebView configuration | `MainActivity.kt` | 2h |
| Header mechanism that reaches all requests | `ForceXWebViewClient.kt` | 1–2 days |
| Block downloads, popups, pickers | `MainActivity.kt`, `ForceXWebChromeClient.kt` | 2h |
| Block external navigation | `ForceXWebViewClient.kt` | 1h |
| Focus-loss and pause blanking | `MainActivity.kt` | 1h |
| Config baking | `Config.kt`, build script | 1 day |
| Build + sign in CI | `.github/workflows/build_apk.yml` | 1 day |
| Real-device testing | manual | 2 days |
| APK download link on gate page and sender pages | `desktop_only.html`, `created.html` | 1h |

### Phase 4 — Windows app polish (2–3 weeks, parallel with Phase 3)

| Task | Files | Effort |
|---|---|---|
| Icon and branding | `forcex_browser.py`, icon files | 1 day |
| Qt-level shortcut blocking | `forcex_browser.py` | 2h |
| Send platform and version headers | `forcex_browser.py` | 1h |
| CI build workflow | `.github/workflows/build_exe.yml` | 1 day |
| Code signing | CI setup | 2 days |
| "Download ForceX for Windows" on dashboard and created page | `dashboard.html`, `created.html` | 1h |

### Phase 5 — UniversalDRM library upgrades (6–8 weeks, separate repo)

| Task | Effort |
|---|---|
| Tile-based page delivery (v0.2) | 2 weeks |
| Per-session rate-limit helpers (v0.2) | 1 week |
| Forensic/invisible watermark (v0.3) | 3 weeks |

---

## 18. File-by-File Change Map

### ForceX repo

| File | Change |
|---|---|
| `backend/models.py` | `protection` accepts `browser`, `app_windows`, `app_android`, `app_any`; audit fields; migration for legacy `"app"` |
| `backend/shares.py` | Parse `platform`; set new protection value |
| `backend/receive.py` | Gate hook for new values; platform to template; watermark text only for `browser`; audit calls |
| `backend/audit.py` | New fields and events (§7) |
| `static/viewer.js` | `alwaysWatermark: true` for browser shares; no watermark option for app shares |
| `templates/sender/new.html` | Platform choice under protection |
| `templates/sender/dashboard.html` | Protection column, audit view, download buttons |
| `templates/sender/created.html` | App download links for app-mode shares |
| `templates/receiver/desktop_only.html` | Platform-specific instructions and download buttons |
| `browser/forcex_browser.py` | Focus-loss blanking, Qt shortcut blocking, headers, branding |
| `build_desktop.py` | Unchanged |
| `android/` | **New**: Kotlin Android project |
| `.github/workflows/build_exe.yml` | **New** |
| `.github/workflows/build_apk.yml` | **New** |
| `tests/` | **New**: server tests |
| `.env.example`, `README.md`, `DEPLOY.md` | Document `FORCEX_ANDROID_DOWNLOAD_URL`, new modes, Android build |

### UniversalDRM repo

| File | Change |
|---|---|
| `universal_drm/render.py` | Accept `None` watermark and skip drawing |
| `universal_drm/static/universal-drm.js` | `alwaysWatermark`; end on `getDisplayMedia`; clipboard clear; no overlay when no watermark |
| `tests/` | Tests for optional watermark |

---

## 19. Open Questions

| Question | Options | Current decision |
|---|---|---|
| How does the Android app get the client key? | Build-time baking vs. first-launch setup code | Build-time for v1; setup code for v2 |
| macOS support? | `NSWindow.sharingType = .none` | Defer to v2 |
| Windows code signing? | Paid Authenticode cert (~$200/yr) vs. self-signed (SmartScreen warning) | Needs decision before public release |
| Play Store vs. sideload? | Play review required for Store | Sideload for v1; Store later |
| Does download-once need an app-only option? | Currently always browser | No: the receiver gets the file anyway |
| What happens when the client key rotates? | Rebuild apps vs. runtime key fetch | Runtime fetch is safer long-term |
| Can protection be changed after creation? | Edit in place vs. revoke and recreate | Revoke and recreate |
| Android minimum SDK? | Choose at project creation | Open |
| Header mechanism on Android? | Cookie via `CookieManager`, or User-Agent suffix | Decide during Phase 3 after testing POST and image requests |
| Does `render_page` already support a `None` watermark? | Check the current code | Verify at the start of Phase 1 |

---

*ForceX × UniversalDRM implementation plan, 2026-10-01.*
