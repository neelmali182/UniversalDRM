# UniversalDRM — Implementation Plan (v2, revised)

> Browser-first, open-source **content protection and capture-resistant sharing** platform for documents, images, presentations, media, and arbitrary files.
>
> *Working title. "DRM" overpromises for documents; see §2.4 on naming.*

**Status:** Planning · **Revision:** 2 (incorporates security review and fixes) · **Target MVP:** v0.1 (PDF + image)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Security Model and Honest Claims](#2-security-model-and-honest-claims)
3. [Goals, Non-Goals, Scope Cuts](#3-goals-non-goals-scope-cuts)
4. [Users and Personas](#4-users-and-personas)
5. [System Architecture](#5-system-architecture)
6. [Technology Stack](#6-technology-stack)
7. [Repository Structure](#7-repository-structure)
8. [Core Domain Design](#8-core-domain-design)
9. [Identity, Shares, Sessions, Tokens](#9-identity-shares-sessions-tokens)
10. [Policy Engine](#10-policy-engine)
11. [Upload and Ingestion Pipeline](#11-upload-and-ingestion-pipeline)
12. [Encryption and Key Management](#12-encryption-and-key-management)
13. [Protection Engines](#13-protection-engines)
14. [Watermarking (Visible and Forensic)](#14-watermarking-visible-and-forensic)
15. [Browser Viewer](#15-browser-viewer)
16. [Anti-Abuse and Suspicious Activity](#16-anti-abuse-and-suspicious-activity)
17. [Audit and Monitoring](#17-audit-and-monitoring)
18. [Database Schema](#18-database-schema)
19. [REST API](#19-rest-api)
20. [SDKs and CLI](#20-sdks-and-cli)
21. [Workers and Sandboxing](#21-workers-and-sandboxing)
22. [Infrastructure and Deployment](#22-infrastructure-and-deployment)
23. [Testing Strategy](#23-testing-strategy)
24. [Threat Model](#24-threat-model)
25. [Roadmap and Milestones](#25-roadmap-and-milestones)
26. [Definition of Done](#26-definition-of-done)
27. [Risks and Open Questions](#27-risks-and-open-questions)
28. [Engineering Rules](#28-engineering-rules)
29. [Appendix](#29-appendix)

---

## 1. Project Overview

### 1.1 The idea

A developer uploads content, defines a protection policy, and receives a **secure URL**. The recipient opens it in an ordinary browser, with no installed app, and views the content under server-enforced rules (expiry, revocation, identity, session limits) plus best-effort deterrence (copy, print, selection) and traceability (watermarks).

### 1.2 One API, one policy model, multiple engines

UniversalDRM does **not** force one technology on every file type. It picks the engine by content type:

```text
                      UniversalDRM
                           |
              +------------+------------+
              |                         |
        Policy Engine            Protection Orchestrator
                                        |
                +-----------------------+-----------------------+
                |                       |                       |
             Media Engine         Document Engine           File Engine
                |                       |                       |
        Packaged CMAF + CBCS    Server-rendered tiles     Envelope encryption
        Multi-DRM (vendor)      + watermark               + authorized download
```

| Content | Protection approach |
|---|---|
| Video / Audio | Encrypted streaming + vendor multi-DRM via EME |
| PDF | Server-rendered, watermarked page tiles (default) |
| PPTX / DOCX | Convert to PDF, then same as PDF |
| Images | Server-side transform, tiling, burned-in watermark |
| TXT / Markdown | Controlled rendering (canvas or sanitized DOM) |
| HTML | Sanitized, sandboxed rendering (deferred; hard problem) |
| ZIP / binary | Encrypted storage + authorized download + per-recipient fingerprinting (later) |

### 1.3 Developer experience (target)

```python
from universaldrm import Client

drm = Client(api_key="udrm_live_xxx")

asset = drm.assets.upload("confidential.pdf")

share = drm.shares.create(
    asset_id=asset.id,
    recipients=["alice@example.com"],       # identity-bound
    policy={
        "view": True,
        "download": False,
        "copy": False,
        "print": False,
        "watermark": {"visible": True, "forensic": True},
        "expires_in": 3600,
        "max_sessions": 1,
    },
)

print(share.url)   # https://udrm.example/v/<token>
```

---

## 2. Security Model and Honest Claims

### 2.1 Five distinct layers

| Layer | Question it answers |
|---|---|
| Access control | Who may access this content? |
| Encryption | Can an attacker with storage access read it? |
| Viewer controls | What can the browser discourage? |
| DRM | Can media play through a hardware/OS-backed pipeline? |
| Capture resistance | How hard is it to capture what is displayed? |

### 2.2 What a browser-only system cannot guarantee

- Screenshot blocking or screen-recording blocking
- Camera capture of the display
- Protection from a compromised OS or malicious browser extension
- Protection after plaintext has been deliberately downloaded

Therefore the product claims **capture resistance and traceability**, never "100% screenshot protection".

### 2.3 Enforced vs best-effort (first-class concept)

Every policy field is tagged by enforcement class, and the API returns that tag so customers cannot mistake deterrence for enforcement.

| Class | Meaning | Examples |
|---|---|---|
| `enforced` | Server refuses the request; holds against a hostile client | expiry, revocation, recipient identity, session/device limits, download=false (no plaintext endpoint exists), page-rate caps |
| `best_effort` | Client-side deterrence; bypassable by a determined user | copy, cut, paste, selection, print, right-click, blur-on-focus-loss |
| `traceability` | Does not prevent capture; identifies the leaker | visible watermark, forensic watermark |

### 2.4 Naming

"DRM" in the name implies Widevine-class guarantees for everything. Candidate renames: *Veilkey*, *Sealview*, *CaptureGuard*, *ShieldShare*. Decide before public launch; also avoids trademark confusion. The repository codename stays `universaldrm` until then.

### 2.5 Honest statements to put in public docs

1. Encryption at rest protects against storage/bucket breaches, not against a compromised API or render worker (they decrypt to render).
2. Copy/print/selection controls are deterrence.
3. DRM licensing comes from a commercial vendor; the project does not include a DRM license server.
4. Widevine L3 (software) on desktop browsers is weaker than L1; set minimum security levels per policy.
5. Device limits use a clearable device secret, so they are a speed bump.

---

## 3. Goals, Non-Goals, Scope Cuts

### 3.1 Goals

- Private storage, encryption at rest, envelope keys, per-tenant KEKs
- Identity-bound, expiring, revocable shares
- Server-side policy enforcement on every request
- Server-rendered, watermarked document/image delivery
- Visible and forensic watermarking
- Sessions, heartbeats, device/session limits
- Audit logging and abuse detection
- Python SDK, REST API, Docker self-hosting
- Later: multi-DRM media, Office conversion, TypeScript SDK, CLI, enterprise identity

### 3.2 Non-goals

1. Building a custom browser CDM or fake DRM
2. Replacing Widevine / PlayReady / FairPlay
3. Promising universal screenshot or screen-recording prevention
4. Preventing camera capture
5. Protecting plaintext that was explicitly downloaded
6. Treating JavaScript restrictions as cryptographic security
7. Inventing cryptographic primitives

### 3.3 Scope cuts from the original plan

The original plan described roughly ten products. The revised sequencing:

| Item | Original | Revised |
|---|---|---|
| v0.1 content types | PDF, text, image, etc. | **PDF + image only** |
| PDF delivery | PDF.js default | **Server-rendered tiles default**; PDF.js = opt-in low-security mode |
| Text / HTML viewers | v0.1 | Deferred (HTML sandboxing is its own project) |
| TypeScript SDK, CLI | v0.1 | Deferred to v0.2+ |
| RBAC, SAML, SCIM | Early | Phase 11 |
| Recipient identity | Implicit | **Mandatory in v0.1** (email OTP) |

---

## 4. Users and Personas

**Developer / Sender.** Owns content, calls the API or SDK, configures policy, creates shares, reads audit logs.

**Recipient.** Opens a URL in Chrome, Edge, Firefox, or Safari. Verifies identity (email OTP or OIDC). No app install for the standard viewer.

**Administrator.** Manages organization, users, API keys, policies, retention, providers; revokes shares and sessions; reads audit logs.

**Security reviewer / auditor** (read-only role). Reads audit events and policy history.

---

## 5. System Architecture

### 5.1 Component view

```text
Developer ──> SDK / REST ──> API Gateway
                                 |
        +------------+-----------+-----------+-------------+
        |            |           |           |             |
      Auth        Assets      Policy     Shares/Sessions  Audit
        |            |           |           |             |
        +------------+-----+-----+-----------+-------------+
                           |
                 Protection Orchestrator ──> Queue (Redis)
                           |                      |
                           |        +-------------+-------------+
                           |        |             |             |
                           |   Doc Worker    Media Worker   Crypto Worker
                           |   (sandboxed)   (sandboxed)
                           v
                  Private Object Storage (S3-compatible)
                           ^
                           |
                    Render / Resource Service
                           ^
                           |
Recipient Browser ──> Viewer App ──> Viewer API (short-lived resource tokens)
```

### 5.2 Request path for a protected resource

```text
Browser
  -> HTTPS
  -> Viewer API
  -> validate resource token (scope, TTL, session binding)
  -> validate session (active, not revoked, policy version)
  -> validate share (not revoked, not expired)
  -> evaluate policy + rate limits
  -> fetch encrypted object -> decrypt in memory
  -> render tile / segment -> burn watermark
  -> respond with Cache-Control: no-store
  -> write audit event
```

### 5.3 Design principles

1. Never invent cryptography or browser DRM.
2. Original assets stay private; there is no permanent plaintext URL.
3. Short-lived, purpose-scoped tokens.
4. Every authorization decision is server-side.
5. Burn watermarks server-side; overlays are decoration only.
6. Tag every claim as `enforced`, `best_effort`, or `traceability`.
7. Sandbox every parser.
8. Tenant isolation is a security boundary (defense in depth: app checks + Postgres RLS).

---

## 6. Technology Stack

### 6.1 Backend

| Concern | Choice | Notes |
|---|---|---|
| Language / framework | Python 3.12, FastAPI | Async, OpenAPI out of the box |
| Validation | Pydantic v2 | Shared models with SDK generation |
| ORM / migrations | SQLAlchemy 2.x, Alembic | Parameterized queries only |
| Database | PostgreSQL 16 | **Row-level security** for tenancy |
| Cache / queue broker | Redis | Also rate limiting |
| Task queue | **Celery** (pick one; do not mix with RQ) | Separate queues per worker class |
| Crypto | `cryptography` (AES-GCM for small blobs), **Google Tink** streaming AEAD for large files | No hand-rolled chunk nonces |
| Password / key hashing | argon2-cffi (passwords), SHA-256/HMAC (high-entropy API keys/tokens) | |

### 6.2 Frontend (viewer)

| Concern | Choice |
|---|---|
| Language / build | TypeScript, React, Vite |
| Rendering | Canvas (tiles), WebGL where useful |
| Media (later) | Shaka Player + EME |
| Doc fallback (opt-in) | PDF.js |
| Client crypto (only if needed) | Web Crypto API |

### 6.3 Document and media processing

| Concern | Choice | Notes |
|---|---|---|
| PDF rasterization | PyMuPDF (MuPDF) or pdfium; Poppler as alternative | Re-render; never pass original through |
| Office conversion | LibreOffice headless | Macros disabled; fonts embedded; conversion preview |
| Image processing | Pillow / libvips | Strip EXIF, resize, tile |
| Malware scan | ClamAV | Plus MIME/magic-byte checks |
| Transcode | FFmpeg | Renditions |
| Packaging | **Shaka Packager** | **CMAF + CBCS** (one encryption pass for Widevine, PlayReady, FairPlay) |
| DRM licensing | Vendor (EZDRM, BuyDRM, PallyCon, Axinom, or similar) | Not open source |

### 6.4 Infrastructure

| Env | Components |
|---|---|
| Dev | Docker Compose: API, viewer, worker, PostgreSQL, Redis, MinIO, ClamAV |
| Prod | App servers, PostgreSQL, Redis, S3/R2/MinIO, CDN, KMS/Vault, reverse proxy, **gVisor or Firecracker** worker sandboxes |
| Observability | OpenTelemetry, Prometheus, Grafana, structured JSON logs |
| CI | GitHub Actions; pip-audit, npm audit, Trivy, SBOM (Syft/CycloneDX) |

### 6.5 Key technical corrections adopted

- CMAF + CBCS instead of plain CENC (cenc); package with Shaka Packager, not raw FFmpeg.
- Tink streaming AEAD for chunked encryption; reusing a nonce under AES-GCM is catastrophic.
- gVisor/Firecracker for Office/FFmpeg workers; non-root containers alone are insufficient.
- Single task queue technology.
- Postgres RLS on every tenant table.

---

## 7. Repository Structure

```text
universaldrm/
├── apps/
│   ├── api/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── routes/
│   │   │   ├── auth.py  assets.py  shares.py  viewer.py
│   │   │   ├── policies.py  drm.py  audit.py
│   │   ├── middleware/
│   │   │   ├── security_headers.py  rate_limit.py  auth.py  tenant.py
│   │   └── services/
│   │       ├── auth_service.py  asset_service.py  policy_service.py
│   │       ├── share_service.py  session_service.py  audit_service.py
│   └── viewer/
│       └── src/
│           ├── api/  components/  layouts/
│           ├── security/   # deterrence + focus handling
│           ├── session/    # heartbeat, token rotation
│           └── viewers/    # PDFViewer, ImageViewer (v0.1); others later
├── packages/
│   ├── core/  crypto/  policy_engine/  sessions/
│   ├── watermark/   # visible + forensic
│   ├── storage/  audit/
│   ├── renderers/   # pdf, image (v0.1); ppt, text later
│   └── drm/         # interface + vendor adapters (later)
├── sdk/
│   ├── python/
│   └── typescript/  # later
├── workers/
│   ├── documents/  media/  crypto/  watermark/  cleanup/
├── tests/
│   ├── unit/  integration/  e2e/  security/  media/
├── docs/
│   ├── architecture/  api/  security/  deployment/  providers/
├── examples/  scripts/  docker/  .github/
├── docker-compose.yml  pyproject.toml  package.json
├── .env.example  LICENSE  SECURITY.md  README.md
```

---

## 8. Core Domain Design

### 8.1 Asset lifecycle

```text
UPLOADING -> UPLOADED -> PROCESSING -> PROTECTED -> ACTIVE
                              |                        |-> REVOKED
                              +-> FAILED               |-> DELETED
```

- `PROTECTED`: processed and encrypted, no share exists yet.
- `ACTIVE`: at least one valid share/policy.
- `DELETED`: storage objects removed and/or tenant key material shredded.

### 8.2 Content classification

Classification uses **magic bytes and parser results**, never the filename extension.

```json
{ "type": "document", "format": "pdf", "engine": "document" }
{ "type": "media",    "format": "video", "engine": "media" }
{ "type": "file",     "format": "archive", "engine": "file" }
```

### 8.3 Provider interfaces

```python
class StorageProvider(Protocol):   # Local, MinIO, S3, R2
class KeyProvider(Protocol):       # Local, AWS KMS, Vault, HSM
class DRMProvider(Protocol):       # vendor adapters
class Renderer(Protocol):          # pdf, image, text, ...
class WatermarkProvider(Protocol): # visible, forensic
class AuditSink(Protocol):         # DB, stdout, SIEM
class IdentityProvider(Protocol):  # email OTP, OIDC, SAML
```

New implementations are added without touching the core API.

---

## 9. Identity, Shares, Sessions, Tokens

### 9.1 Token classes (never reuse across purposes)

| Token | Purpose | TTL | Stored |
|---|---|---|---|
| API key | Developer auth | Until revoked | Hash only |
| Share token | Opens landing page | Per share | Hash only |
| Verification token / OTP | Recipient identity proof | 5–10 min | Hash only |
| Viewer session token | Bound to one session | Session TTL | Server-side record |
| Resource token | Fetch one tile/page/segment | 30–120 s, rotating | Stateless signed, plus session check |
| DRM authorization token | License request | Seconds to minutes | Stateless signed |

All tokens: high entropy, scoped, revocable, purpose-specific.

### 9.2 Recipient binding (fixes link forwarding)

A forwarded URL must not equal a verified recipient.

```text
1. Sender creates share with recipients = [emails] (or "any authenticated" / OIDC tenant)
2. Recipient opens URL -> landing page (no session yet, no consumption)
3. Recipient enters email -> must match allowlist -> OTP / magic link sent
4. Recipient submits OTP (explicit POST)
5. Session created, bound to verified identity
6. Watermark displays verified identity
```

Optional: an "open link" mode with no identity, for low-risk content, with the watermark labelled "unverified".

### 9.3 One-time links must survive link scanners

Email/Slack/antivirus scanners fetch URLs automatically.

- **Never consume on GET.** The landing page is inert.
- Consume only on an explicit `POST /v1/viewer/sessions` after a human action (button, OTP submit).
- Add lightweight bot checks on the landing page (user-agent heuristics, optional challenge).
- "One-time" means one *session creation*, not one HTTP request.

### 9.4 Session lifecycle

```text
landing -> verify identity -> create session -> load viewer -> heartbeats -> expire/revoke
```

- Session bound to: asset, share, user, policy version, device secret, expiry.
- Heartbeat every 15–30 s returns `{active, expires_at, revoked}`; viewer tears down content on `active=false`.
- Revocation: `DELETE /v1/shares/{id}` marks the share revoked; sessions are invalidated according to policy (immediate by default).
- Resource tokens are rejected the moment the session is non-active, even if the token TTL has not elapsed (session check on every request).

### 9.5 Device control

- Server issues a random **device secret** stored in a first-party, httpOnly cookie (with an IndexedDB fallback).
- `max_devices` counts distinct device secrets per share.
- Documented as clearable: a speed bump, not a wall. No invasive fingerprinting.

### 9.6 Authentication roadmap

v0.1 API keys (hashed) → OAuth2/OIDC → SAML → SCIM.

---

## 10. Policy Engine

### 10.1 Schema

```json
{
  "version": 1,
  "enforced": {
    "view": true,
    "download": false,
    "expires_in": 3600,
    "one_time": false,
    "max_sessions": 1,
    "max_devices": 1,
    "recipients": ["alice@example.com"],
    "rate_limits": { "pages_per_minute": 20, "max_pages_total": 200 },
    "min_drm_security_level": "L1"
  },
  "best_effort": {
    "copy": false,
    "cut": false,
    "paste": false,
    "selection": false,
    "print": false,
    "context_menu": false,
    "blur_on_focus_loss": true
  },
  "traceability": {
    "watermark": {
      "visible": { "type": "tiled", "fields": ["user", "session", "timestamp"], "opacity": 0.15 },
      "forensic": { "enabled": true }
    }
  }
}
```

API responses echo each field's class so SDK users see what is enforced.

### 10.2 Evaluation

```python
decision = policy_engine.evaluate(user, asset, share, session, action)
# -> Decision(allowed=False, reason="session_expired", enforcement="enforced")
```

Order: authentication -> tenant/ownership -> share validity -> identity -> session -> expiry -> rate limits -> policy action -> allow/deny. Every decision writes an audit event when denied.

### 10.3 Versioning

Each change creates a new immutable policy version. Sessions record `policy_version`; the owner can choose "apply to new sessions only" or "invalidate active sessions".

### 10.4 Security levels

| Level | Adds |
|---|---|
| 0 Basic | TLS, auth, authz, private storage, expiry |
| 1 Protected viewer | Visible watermark, deterrence, recipient OTP |
| 2 Strict | Forensic watermark, short sessions, device/session limits, scraping limits, capture heuristics |
| 3 Media DRM | Level 2 + encrypted CMAF/CBCS + vendor DRM + min security level |

---

## 11. Upload and Ingestion Pipeline

```text
Client -> (resumable/multipart upload to staging)
  -> size limit
  -> magic-byte + MIME detection (filename ignored)
  -> ClamAV scan
  -> sandboxed parse (structure validation)
  -> classification
  -> Protection Orchestrator
  -> encryption
  -> private storage
  -> asset state: PROTECTED
```

Details:

- Staging bucket is separate from the final bucket; staged plaintext is deleted after processing.
- Large files: multipart/resumable uploads direct to object storage via presigned part URLs; never buffer whole files in API RAM.
- PDFs are **re-rendered**, not passed through; active content (JS, embedded files, launch actions) is discarded.
- Images: strip EXIF/GPS, bound pixel dimensions (decompression-bomb limit).
- Office files: macros disabled, conversion in a network-less sandbox, strict timeout.

---

## 12. Encryption and Key Management

### 12.1 Envelope hierarchy

```text
Root (KMS / Vault / HSM)
   └── Per-tenant KEK
          └── Per-asset (or per-version) DEK
                 └── AES-256-GCM / Tink streaming AEAD over content
```

- **Per-tenant KEK** enables **crypto-shredding**: destroying a tenant's KEK renders all their data unrecoverable.
- DEKs stored only wrapped; unwrap happens in the crypto/render worker memory.
- Use AAD binding (asset id, version, tenant) so ciphertext cannot be swapped between assets.

### 12.2 Key provider

```python
class KeyProvider(Protocol):
    def create_tenant_kek(self, tenant_id): ...
    def wrap_dek(self, tenant_id, dek, aad) -> bytes: ...
    def unwrap_dek(self, tenant_id, wrapped, aad) -> bytes: ...
    def rotate_kek(self, tenant_id): ...
```

Implementations: `LocalKeyProvider` (dev only), `AWSKMSKeyProvider`, `VaultKeyProvider`, `HSMKeyProvider`.

### 12.3 Large-file encryption

Use Tink streaming AEAD (or a STREAM construction): per-segment keys/nonces derived safely, truncation-resistant, random-access decryption. Do not write a custom chunked GCM.

### 12.4 What encryption does and does not do

Documented plainly: protects against bucket/database breaches and lost backups. It does not protect against a compromised API/render server, because those decrypt to serve content.

### 12.5 Rotation and deletion

- KEK rotation: re-wrap DEKs lazily or by background job.
- Asset deletion: delete objects, delete wrapped DEK, write audit tombstone.
- Tenant deletion: shred KEK.

---

## 13. Protection Engines

### 13.1 Document engine (v0.1 core)

**Default mode: server-rendered tiles.**

```text
Authorized request -> decrypt PDF (memory)
  -> rasterize page at policy-limited DPI
  -> burn visible watermark
  -> apply forensic watermark
  -> tile (e.g., 512x512 WebP/PNG), optionally scrambled order
  -> respond no-store
```

| Mode | Original sent to browser? | Text search / a11y | Use |
|---|---|---|---|
| **Tiles (default)** | No | Lost | Strict |
| PDF.js (opt-in, low-security) | Yes (the whole file) | Kept | Low-risk content |
| Accessible mode (opt-in) | No | Watermarked text layer | Accessibility compliance |

Page-level authorization, per-session page-rate limits, and resolution caps apply.

### 13.2 Image engine

Validate -> strip metadata -> resolution limit by policy -> viewport-based tiled delivery -> burned watermark -> short-lived tiles. Full-resolution originals are never exposed.

### 13.3 Presentation and Word (v0.2)

```text
PPTX/DOCX -> sandboxed LibreOffice -> PDF -> document engine
```

Mitigations for fidelity: embed fonts, show a conversion preview to the sender before sharing, document unsupported features (SmartArt, animations, some transitions).

### 13.4 Text / Markdown (later)

Canvas rendering or sanitized DOM; treat as best-effort.

### 13.5 HTML (deferred)

Requires strict sanitization plus sandboxed iframe with a separate origin and CSP. Out of scope until core is stable.

### 13.6 Media engine (v0.3+)

```text
Validate -> FFmpeg renditions (360/480/720/1080)
  -> Shaka Packager: CMAF, CBCS, (HLS + DASH)
  -> key registration with DRM vendor
  -> secure manifest
  -> Shaka Player + EME
```

- Manifests and segments are fetched with authorized, short-lived URLs.
- License requests go through UniversalDRM first (session, policy, expiry, revocation, device checks) and then to the vendor.
- Set a **minimum security level** in license policy (e.g., require Widevine L1 for 1080p); fall back to lower resolution on L3.
- FairPlay requires Apple's approval process; start early.
- Forensic watermarking for video: A/B segment variants through the DRM/CDN vendor.

### 13.7 File engine

Arbitrary files are encrypted and stored; no viewer unless a safe renderer exists. Delivery: authorized download. Optional per-recipient fingerprinting (invisible modifications of PDFs/Office files) so a leak traces to a person, while stating plainly that plaintext can escape.

### 13.8 Experimental: documents as DRM video

Render pages into short encrypted video segments and play through EME. On hardware-DRM platforms (Widevine L1, FairPlay on Safari, PlayReady SL3000) the OS can black out screenshots. Expensive, platform-limited, poor for text fidelity and accessibility. Research spike only; do not plan the MVP around it.

### 13.9 Optional native strict mode (future)

Desktop/mobile wrapper using OS capture exclusion (Windows display affinity, Android `FLAG_SECURE`, iOS screen-capture detection) for high-security customers.

---

## 14. Watermarking (Visible and Forensic)

### 14.1 Visible watermark

- Burned into pixels **server-side** on every tile; a DOM overlay is additional only.
- Content: verified recipient identity, session id (short), timestamp, organization label.
- Tiled, diagonal, semi-transparent; randomized offsets per session to defeat averaging/cropping.

### 14.2 Forensic (invisible) watermark

Visible marks can be cropped or painted out. Add an invisible mark encoding a **payload id** (maps to session/recipient):

- Raster: frequency-domain (DCT/DWT) spread-spectrum embedding in tiles; robust to JPEG, resize, mild crop.
- Text layout: imperceptible spacing/kerning perturbations (for text-heavy documents).
- Video: A/B segment sequences via vendor.
- Detection tool: given a leaked image, extract payload and look up the session. Ship this as an admin utility.

Honest statement: robust against casual edits; not against a determined adversary with multiple differing copies (collusion) or heavy processing.

### 14.3 Interface

```python
class WatermarkProvider(Protocol):
    def payload_for(self, session) -> bytes: ...
    def render_visible(self, image, session, policy) -> Image: ...
    def embed_forensic(self, image, payload) -> Image: ...
    def extract(self, image) -> Optional[bytes]: ...
```

---

## 15. Browser Viewer

### 15.1 Boot flow

```text
GET /v/{token}           -> inert landing page
POST identity/OTP        -> verified
POST /viewer/sessions    -> session + viewer config + device cookie
choose viewer by content type
fetch tiles via resource tokens (auto-rotating)
heartbeat loop
```

The viewer receives only: viewer config, session id, short-lived tokens, policy (with enforcement classes), watermark data. It **never** receives permanent asset URLs, storage credentials, or key material.

### 15.2 Deterrence layer (`best_effort`)

- Block `copy`, `cut`, `paste`, `contextmenu`, `dragstart`, `selectstart` events
- Intercept common shortcuts (Ctrl/Cmd + C/X/A/P/S)
- `user-select: none`; no editable surfaces
- `@media print { body { display: none } }` and `beforeprint`/`afterprint` handling
- Canvas rendering of tiles (no DOM text)
- Focus/visibility handling: blur or hide on `visibilitychange`/`blur`, require reactivation
- Each trigger emits a `*_ATTEMPT` audit event

Copy in UI and docs: **"attempt detected"**, never "copy prevented".

### 15.3 Browser security headers

HSTS, strict CSP (no inline scripts, no third-party origins), `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, COOP/CORP, `Cache-Control: no-store` on protected resources, frame-ancestors restrictions.

### 15.4 Capability detection

Detect Canvas, WebGL, EME, MediaCapabilities, fullscreen. Used for compatibility routing only, never as a security proof.

### 15.5 Accessibility

Tile-only viewing excludes screen-reader users. Provide an opt-in accessible mode (watermarked text layer) and document the tradeoff so customers can choose per policy.

---

## 16. Anti-Abuse and Suspicious Activity

### 16.1 Bulk scraping with a valid session

A legitimate session can request every page in seconds.

- Per-session and per-share `pages_per_minute` and `max_pages_total`
- Sequential-access heuristics (faster than human reading rate, perfectly linear paging, no dwell time)
- Tile request bursts
- Violations add to a suspicion score, then throttle -> challenge -> auto-revoke

### 16.2 Signals

Many session creations; repeated expired/revoked token use; rapid device switching; excessive license requests; impossible geo changes; token replay from a different device; bursts of deterrence-event attempts.

### 16.3 Scoring

```text
Signals -> weighted score -> { normal | watch | throttle | challenge | revoke }
```

Never act on one weak signal. All actions are audited and configurable per policy.

### 16.4 Platform rate limiting

Redis-backed limits on `/auth`, `/share`, `/viewer`, `/license`, `/api`, keyed by IP, API key, share, and session.

---

## 17. Audit and Monitoring

### 17.1 Event catalog

```text
ASSET_CREATED  ASSET_UPLOADED  ASSET_PROTECTED  ASSET_DELETED
SHARE_CREATED  SHARE_OPENED    SHARE_REVOKED
RECIPIENT_VERIFIED  RECIPIENT_VERIFY_FAILED
VIEWER_STARTED  VIEWER_HEARTBEAT  VIEWER_EXPIRED  VIEWER_REVOKED
COPY_ATTEMPT  PRINT_ATTEMPT  DOWNLOAD_ATTEMPT  FOCUS_LOST
POLICY_DENIED  RATE_LIMITED
DRM_LICENSE_REQUEST  DRM_LICENSE_DENIED
SUSPICIOUS_ACTIVITY  WATERMARK_TRACE_LOOKUP
```

Rule: **Attempt detected != action prevented.** Event names and docs must not claim prevention for best-effort controls.

### 17.2 Audit integrity

Append-only table; optional hash chaining (each record includes the hash of the previous) and export to an external sink for tamper evidence.

### 17.3 Metrics

`assets_created_total`, `viewer_sessions_active`, `policy_denials_total`, `copy_attempts_total`, `tile_requests_total`, `scrape_throttles_total`, `drm_license_requests_total`, `processing_failures_total`, plus latency histograms for render and license endpoints.

### 17.4 Privacy and retention

Collect the minimum. Configurable retention for audit logs, IPs, sessions, and device data. No permanent browser fingerprinting.

---

## 18. Database Schema

All tenant-owned tables include `organization_id` and have **RLS policies** (`organization_id = current_setting('app.org_id')::uuid`). The API sets `app.org_id` per request/transaction.

```text
organizations(id, name, kek_ref, created_at)
users(id, organization_id, email, password_hash, role, created_at)
api_keys(id, organization_id, key_hash, prefix, name, scopes, created_at, expires_at, revoked_at)

assets(id, organization_id, name, mime_type, size, content_type, status, created_at, updated_at)
asset_versions(id, asset_id, version, storage_key, wrapped_dek, kek_version,
               checksum, page_count, created_at)
protection_policies(id, asset_id, version, policy_json, created_at)

shares(id, asset_id, organization_id, token_hash, policy_version, recipients_json,
       identity_mode, expires_at, one_time, consumed_at, revoked, created_at)
recipient_verifications(id, share_id, email, otp_hash, attempts, expires_at, verified_at)

viewer_sessions(id, asset_id, share_id, organization_id, verified_email, device_secret_hash,
                created_at, expires_at, last_seen, status, policy_version, watermark_payload)
device_bindings(id, share_id, device_secret_hash, first_seen, last_seen)

drm_assets(id, asset_id, provider, manifest_key, key_id, created_at)
drm_licenses(id, drm_asset_id, session_id, provider, created_at, expires_at, status)

jobs(id, organization_id, asset_id, type, state, attempts, error, created_at, updated_at)
audit_events(id, organization_id, asset_id, user_id, session_id, event_type,
             metadata, ip, user_agent, prev_hash, created_at)
```

Indexes: `shares.token_hash` (unique), `viewer_sessions(share_id, status)`, `audit_events(organization_id, created_at)`, `assets(organization_id, status)`.

---

## 19. REST API

Versioned under `/v1`. OpenAPI generated from FastAPI; SDKs generated/validated from it.

### Assets
```http
POST   /v1/assets                       # create + start upload (returns upload URLs)
POST   /v1/assets/{id}/complete         # finish upload, enqueue processing
GET    /v1/assets/{id}
DELETE /v1/assets/{id}
POST   /v1/assets/{id}/protect
GET    /v1/assets/{id}/protection       # status, job progress, conversion preview
```

### Policies
```http
POST   /v1/assets/{id}/policies         # new version
GET    /v1/assets/{id}/policies
```

### Shares
```http
POST   /v1/assets/{id}/shares
GET    /v1/shares/{id}
DELETE /v1/shares/{id}                  # revoke
```

### Recipient and viewer
```http
GET    /v/{token}                       # inert landing page (never consumes)
POST   /v1/viewer/verify/start          # send OTP
POST   /v1/viewer/verify/confirm        # check OTP
POST   /v1/viewer/sessions              # create session (consumes one-time)
POST   /v1/viewer/sessions/{id}/heartbeat
DELETE /v1/viewer/sessions/{id}
```

### Content
```http
GET /v1/viewer/assets/{id}/meta
GET /v1/viewer/assets/{id}/page/{n}/tile/{x}/{y}     # resource-token authorized
GET /v1/viewer/assets/{id}/manifest                   # media
GET /v1/viewer/assets/{id}/resource/{resource}
```

### DRM and audit
```http
POST /v1/drm/license/{provider}
GET  /v1/assets/{id}/audit
GET  /v1/sessions/{id}/audit
POST /v1/forensics/trace                # upload leaked image -> payload -> session
```

Conventions: idempotency keys on create endpoints, cursor pagination, consistent error envelope, policy fields returned with enforcement class.

---

## 20. SDKs and CLI

### 20.1 Python SDK (v0.1)

Modules: `assets`, `shares`, `sessions`, `policies`, `audit`, `forensics`. Handles resumable upload, polling for processing, typed models from OpenAPI.

### 20.2 TypeScript SDK (v0.2+)

```typescript
const drm = new UniversalDRM({ apiKey: process.env.UDRM_KEY! });
const asset = await drm.assets.upload("secret.pdf");
const share = await drm.shares.create(asset.id, {
  recipients: ["alice@example.com"],
  policy: { download: false, expiresIn: 600 },
});
```

### 20.3 CLI (v0.2+)

```bash
udrm login
udrm upload secret.pdf
udrm share asset_123 --to alice@example.com --expires 1h
udrm revoke share_123
udrm sessions
udrm audit asset_123
udrm trace leaked.png
```

---

## 21. Workers and Sandboxing

### 21.1 Worker classes and queues

| Queue | Jobs |
|---|---|
| `documents` | RENDER_PDF, CONVERT_PPT, CONVERT_DOC, EXTRACT_METADATA |
| `media` | TRANSCODE_VIDEO, PACKAGE_MEDIA |
| `crypto` | ENCRYPT_ASSET, REKEY, DELETE_ASSET |
| `scan` | MALWARE_SCAN |
| `maintenance` | cleanup, retention, audit export |

Job states: `QUEUED -> PROCESSING -> COMPLETED | FAILED | CANCELLED`. Retries with backoff; poison-job quarantine.

### 21.2 Sandbox profile (parsers: LibreOffice, FFmpeg, PDF/image libs)

- Runtime: **gVisor (runsc) or Firecracker microVMs**
- Non-root, read-only root filesystem, ephemeral tmpfs workspace
- No network (or strict egress deny), no production secrets
- CPU/memory/pids limits, wall-clock timeout, output-size limits
- seccomp/AppArmor profiles
- Office: macros disabled, no external links/OLE
- Input fetched via presigned URL; output written back; container destroyed after each job

### 21.3 Render workers versus decrypt exposure

Render workers hold plaintext briefly. Keep them separate from the public API process, with least-privilege access to unwrap only needed DEKs, and log every unwrap.

---

## 22. Infrastructure and Deployment

### 22.1 Dev: Docker Compose

```text
api, viewer, worker-documents, postgres, redis, minio, clamav, mailhog (OTP emails)
```

### 22.2 Production

```text
Internet -> CDN -> Reverse proxy -> API / Viewer
                                  -> Redis, PostgreSQL (HA)
                                  -> S3-compatible storage (private bucket)
                                  -> KMS/Vault
                                  -> Sandboxed worker pool
```

CDN rules: only short-lived signed URLs; `no-store` for protected tiles unless a revocation-safe caching strategy is designed; never turn a private asset into a public cached object.

### 22.3 Configuration

```env
APP_ENV=development
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
STORAGE_PROVIDER=minio
STORAGE_ENDPOINT=http://minio:9000
STORAGE_BUCKET=universaldrm
KMS_PROVIDER=local          # dev only
SESSION_TTL=600
RESOURCE_TOKEN_TTL=60
SHARE_TTL=600
MAX_UPLOAD_MB=500
OTP_TTL=600
```

Secrets: `.env` in dev only; KMS/Vault/cloud secret manager in production. Never commit secrets.

### 22.4 CI/CD

PR pipeline: lint (ruff, eslint) -> type check (mypy, tsc) -> unit tests -> integration tests (compose) -> security tests -> dependency scan (pip-audit, npm audit, Trivy) -> SBOM -> Docker build -> release. Dependabot/Renovate enabled.

### 22.5 Backup and DR

Encrypted DB backups, object-storage versioning with lifecycle rules, tested restores, documented RPO/RTO; ensure backups respect crypto-shredding (backups must not hold unwrapped keys).

---

## 23. Testing Strategy

### 23.1 Layers

- **Unit:** crypto wrappers, token signing/verification, policy evaluation, watermark embed/extract, permission checks
- **Integration:** upload -> protect -> share -> verify -> session -> tile -> expire -> audit
- **E2E (Playwright):** Chrome, Edge, Firefox, WebKit
- **Security:** see below
- **Media (later):** manifest auth, license auth, expiry, wrong user/session, revoked session

### 23.2 Security test list

Expired/revoked token, token replay, cross-tenant IDOR, path traversal, MIME confusion, decompression bombs, oversized upload, malicious PDF/Office, XSS, CSRF, SSRF, SQL injection, rate-limit bypass, session fixation, OTP brute force, **link-scanner prefetch does not consume one-time link**, **scraping limits trigger**, **RLS denies cross-tenant queries even with app-layer bug (test with app checks disabled)**.

### 23.3 Viewer tests

Tests must assert the right thing:

| Test | Asserts |
|---|---|
| Copy/print/selection | Attempt **detected** and audited |
| Download | No plaintext endpoint exists (**enforced**) |
| Watermark | Present in tile pixels, survives DOM removal |
| Forensic | Payload recovered after JPEG/resize/crop test suite |
| Expiry | Resource requests return 403 after expiry, viewer closes |

---

## 24. Threat Model

| # | Threat | Mitigations |
|---|---|---|
| 1 | Direct storage access | Private buckets, no public URLs, encryption, server authz |
| 2 | Expired link reuse | Server-side expiry, short sessions |
| 3 | Revoked share reuse | Share check on every request, session revocation |
| 4 | Token replay | Short TTL, rotation, session + device binding |
| 5 | IDOR / cross-tenant | Object-level authz, Postgres RLS, explicit tests |
| 6 | XSS | Strict CSP, output encoding, sanitization, sandboxed origins |
| 7 | Malicious Office/PDF | gVisor/Firecracker, no network, re-render, macros off |
| 8 | SQL injection | ORM, parameterization, validation |
| 9 | Malware upload | Magic bytes, ClamAV, sandbox |
| 10 | Link forwarding | Recipient-bound OTP, verified watermark identity |
| 11 | Link-scanner burning | No consumption on GET |
| 12 | Watermark removal | Server-burned + forensic watermark |
| 13 | Bulk scraping | Rate caps, heuristics, auto-revoke |
| 14 | Malicious insider/render-server compromise | Least-privilege key unwrap, unwrap logging, separate workers |
| 15 | Screenshot/camera capture | **Not preventable**; traceability + (media) hardware DRM |
| 16 | OTP brute force | Attempt limits, lockouts, rate limiting |
| 17 | Collusion attacks on watermark | Documented limitation; per-session unique payloads aid detection |

---

## 25. Roadmap and Milestones

### Phase 0 — Foundation (weeks 1–2)
Monorepo, FastAPI skeleton, Postgres + RLS scaffolding, Redis, MinIO, Docker Compose, CI, logging, config.

### Phase 1 — Assets (weeks 3–4)
Upload API (resumable), magic-byte/MIME, ClamAV, envelope encryption with LocalKeyProvider, asset lifecycle, jobs.

### Phase 2 — Policy + Shares + Identity (weeks 5–6)
Policy schema with enforcement classes, evaluation, versions; shares; email OTP; no-consume-on-GET; sessions; token classes.

### Phase 3 — PDF/Image Viewer (weeks 7–9)
Sandboxed rasterizer, tiled delivery, server-burned visible watermark, React viewer, deterrence layer, heartbeat, rate limits, audit events.

### Phase 4 — Sessions, Audit, Revocation (weeks 10–11)
Revocation flows, device secret, session/device limits, audit viewer, scraping heuristics, suspicion scoring.

### Phase 5 — Forensic Watermark (weeks 12–13)
Embed/extract for raster tiles, trace endpoint and admin tool, robustness test suite.

**Milestone: v0.1 release (PDF + image).**

### Phase 6 — Office/Docs (v0.2)
LibreOffice pipeline in sandbox, conversion preview, PPTX/DOCX, TypeScript SDK, CLI, accessible mode.

### Phase 7 — File Protection
Tink streaming encryption, authorized encrypted downloads, large-file support, optional per-recipient fingerprinting.

### Phase 8 — Media (v0.3)
FFmpeg renditions, Shaka Packager (CMAF + CBCS), HLS/DASH, Shaka Player, media authorization.

### Phase 9 — DRM (v0.4)
DRMProvider interface, first vendor (Widevine), license authorization, min security level, DRM audit, vendor forensic watermark.

### Phase 10 — Multi-DRM (v0.5)
PlayReady, FairPlay (start Apple approval early), capability routing.

### Phase 11 — Enterprise
Orgs, RBAC, OIDC, SAML, SCIM, advanced audit, compliance controls.

### Phase 12 — Production security
KMS/Vault/HSM, penetration test, backups/DR, SBOM, supply-chain security, rename/branding, public docs on limitations.

### Research spikes (parallel, non-blocking)
Documents-as-DRM-video; native strict mode; collusion-resistant watermark codes.

---

## 26. Definition of Done

### Core release

```text
[ ] Developer can create API key
[ ] Developer can upload asset (resumable)
[ ] Asset classified by magic bytes, validated, scanned
[ ] Asset encrypted (per-tenant KEK -> DEK) and stored privately
[ ] Policy configurable; fields tagged enforced / best_effort / traceability
[ ] Share creation with recipient binding
[ ] Landing page never consumes one-time links (verified by prefetch test)
[ ] Recipient OTP verification works; OTP brute-force protected
[ ] Viewer session created on explicit POST
[ ] Policy enforced server-side on every resource request
[ ] Resource tokens short-lived and session-bound
[ ] Visible watermark burned into pixels server-side
[ ] Forensic watermark embed + trace tool works on test corpus
[ ] Copy/selection/print/download ATTEMPTS detected and audited (docs say "deterrence")
[ ] Download: no plaintext endpoint exists (enforced)
[ ] Scraping limits trigger throttle/revoke
[ ] Session expires; revocation takes effect immediately
[ ] Audit events generated; retention configurable
[ ] Tenant isolation enforced at app layer AND Postgres RLS (tested independently)
[ ] Security headers enabled; rate limits enabled
[ ] Sandboxed workers (gVisor/Firecracker) for parsers
[ ] Security test suite passes
[ ] Docker deployment works; Python SDK works; API docs published
[ ] Public docs state limitations honestly
```

### Media additions

```text
[ ] ABR renditions; CMAF + CBCS packaging
[ ] HLS/DASH manifests authorized and short-lived
[ ] Vendor DRM integrated; license authorization applies session policy
[ ] Minimum security level enforced per policy
[ ] Forensic watermark (A/B) through vendor
```

---

## 27. Risks and Open Questions

| Risk / question | Impact | Plan |
|---|---|---|
| Users expect screenshot blocking | Reputation, legal claims | Honest docs, enforcement-class tags, UI wording |
| Tile rendering cost (CPU, storage, bandwidth) | Cost, latency | Render caching keyed by (asset, page, dpi, watermark-free base) with per-session watermark applied on top; evaluate GPU/libvips |
| Forensic watermark robustness | Trace failures | Build test corpus early (screenshots, phone photos, recompression); be explicit about limits |
| Accessibility vs. protection | Compliance | Opt-in accessible mode; policy documents tradeoff |
| Office conversion fidelity | Customer trust | Preview step, embedded fonts, documented gaps |
| DRM vendor lock-in and cost | Margin, flexibility | DRMProvider abstraction; evaluate 2 vendors |
| FairPlay approval lead time | Schedule | Start application in Phase 8 |
| Name/trademark ("DRM") | Branding | Rename decision before launch |
| Caching and revocation with CDN | Leak window | `no-store` default; short TTL signed URLs if caching is enabled |
| Legal: recipient data, GDPR | Compliance | Data minimization, retention controls, DPA template |

Open decisions:

1. Final product name.
2. Pick the PDF rasterizer (PyMuPDF licensing is AGPL/commercial; pdfium is permissive; choose with licensing in mind).
3. Default tile size and format (WebP vs PNG) versus forensic watermark robustness.
4. First DRM vendor.
5. Project license (Apache-2.0 vs AGPL) considering the rasterizer dependency.

---

## 28. Engineering Rules

1. Never expose originals as permanent public URLs.
2. Never put master keys or wrapped keys in browser code.
3. Never rely on frontend authorization.
4. Never claim JavaScript gives OS-level DRM.
5. Never invent cryptographic algorithms or nonce schemes.
6. Never build a fake CDM; use established DRM for browser media.
7. Use server-burned watermarks; overlays are cosmetic.
8. Tag every policy field as `enforced`, `best_effort`, or `traceability`.
9. Short-lived, purpose-specific tokens; never reuse token classes.
10. Never consume state on GET.
11. Sandbox every parser and converter.
12. Treat tenant isolation as a security boundary with RLS.
13. Log security events; "attempt detected" is not "prevented".
14. Test every authorization path server-side.
15. Document browser-security limits clearly and publicly.

---

## 29. Appendix

### A. Example: end-to-end v0.1 flow

```text
Developer uploads PDF -> validate -> scan -> sandbox re-render check -> encrypt -> store
Developer sets policy + creates share for alice@example.com
Alice opens URL (inert landing, nothing consumed)
Alice enters email -> OTP -> confirms (POST)
Session created (bound to alice, device secret, policy v1)
Viewer requests tiles with rotating resource tokens
Server decrypts in memory, rasterizes, burns visible mark, embeds forensic payload, responds no-store
Heartbeats every ~20 s; scraping heuristics run
Session expires or sender revokes -> tile requests 403 -> viewer closes
Audit trail records the whole sequence
Leaked screenshot later -> /v1/forensics/trace -> payload -> session -> alice
```

### B. Protection matrix

| Technique | Purpose | Guarantee |
|---|---|---|
| Server authorization | Restrict access | Strong (enforced) |
| Expiry / revocation | Limit lifetime | Strong (enforced) |
| Recipient OTP/OIDC | Bind identity | Strong (enforced), subject to recipient account security |
| Encryption at rest | Storage breach protection | Strong, but not against compromised servers |
| Short-lived resource tokens | Limit reuse | Strong when enforced server-side |
| Rate limits / scraping caps | Limit bulk extraction | Moderate |
| Server-burned visible watermark | Traceability | Deters; croppable |
| Forensic watermark | Traceability | Robust to casual edits; not collusion |
| Copy/select/print blocking | Deter casual use | None (best-effort) |
| Canvas/tile rendering | Raise effort for extraction | None |
| Media DRM | Protect playback | Stronger; platform-dependent (L1 > L3) |
| OS capture exclusion (native) | Block capture | Platform-specific |

### C. Content-type matrix

| Content | Storage | Viewer | Main protection |
|---|---|---|---|
| Video / Audio | Encrypted | Shaka + EME | CMAF/CBCS + vendor DRM |
| PDF | Encrypted | Tile viewer | Server render + watermarks |
| PPTX / DOCX | Encrypted | Tile viewer | Sandboxed convert + render |
| Image | Encrypted | Tile viewer | Tiling + watermarks |
| TXT / MD | Encrypted | Text viewer | Canvas/sanitized DOM |
| HTML | Encrypted | Sandbox viewer | Sanitize + isolate (deferred) |
| ZIP / binary | Encrypted | None | Authorized download (+ fingerprinting) |

### D. Project statement

UniversalDRM is an open-source, browser-first content protection and capture-resistant sharing platform. It combines identity-bound access, server-enforced policy, envelope encryption, controlled server-side rendering, server-burned and forensic watermarking, audit, and vendor-backed media DRM behind **one API and one policy model**, and it prioritizes **technically achievable security over exaggerated claims**.
