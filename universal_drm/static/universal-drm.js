/*
 * UniversalDRM viewer. No dependencies, works under a strict CSP (script-src 'self').
 *
 *   const viewer = UniversalDRM.mount(element, {
 *     kind: 'pages',                     // or 'video'
 *     pages: 12, pageUrl: i => `/doc/page/${i}`,
 *     videoUrl: '/doc/video', videoType: 'video/mp4',
 *     watermark: 'Alice · #1a2b3c',      // temporary watermark for detected capture-related signals
 *     statusUrl: '/doc/status',          // polled; a non-2xx reply or {active:false} wipes the content
 *     statusInterval: 15,
 *     onEnd: reason => {}
 *   });
 *
 * Best-effort capture deterrence:
 * - Webpage images remain clean during normal viewing.
 * - The viewer can react to browser-visible signals such as screenshot keys, focus loss,
 *   printing, or getDisplayMedia calls. It cannot reliably detect external recorders.
 * - A capture may therefore contain no watermark; this is not capture prevention.
 */
(function (global) {
  'use strict';

  function drawWatermark(ctx, w, h, text, style) {
    if (!text || w <= 0 || h <= 0) return;
    style = style || {};
    const size = Math.max(13, Math.round(w / 42));
    ctx.save();
    ctx.font = `600 ${size}px sans-serif`;
    ctx.translate(w / 2, h / 2);
    ctx.rotate(-Math.PI / 6);
    const stepX = ctx.measureText(text).width + size * 4, stepY = size * 6, span = Math.hypot(w, h);

    if (style.stroke) {
      ctx.strokeStyle = style.stroke;
      ctx.lineWidth = Math.max(1.5, Math.round(size / 7));
      ctx.lineJoin = 'round';
      for (let y = -span, row = 0; y < span; y += stepY, row++) {
        const offset = (row % 2) * stepX / 2;
        for (let x = -span + offset; x < span; x += stepX) {
          ctx.strokeText(text, x, y);
        }
      }
    }

    ctx.fillStyle = style.fill || 'rgba(128,128,128,0.22)';
    for (let y = -span, row = 0; y < span; y += stepY, row++) {
      const offset = (row % 2) * stepX / 2;
      for (let x = -span + offset; x < span; x += stepX) {
        ctx.fillText(text, x, y);
      }
    }
    ctx.restore();
  }

  function stamp(text) { return `${text} · ${new Date().toLocaleString()}`; }

  function mount(root, opts) {
    const o = Object.assign({
      statusInterval: 15,
      watermark: '',
      alwaysWatermark: false,
      onEnd: function () {},
      blackoutOnCapture: true,
      endOnCapture: false
    }, opts);
    const listeners = [], timers = [];
    const activePages = new Set();
    let ended = false, observer = null, video = null, videoOverlay = null;
    let animId = null, frameCount = 0;
    let captureMode = false, captureTimer = null;

    const on = (target, type, fn, capture) => {
      target.addEventListener(type, fn, capture);
      listeners.push([target, type, fn, capture]);
    };
    const stop = e => e.preventDefault();

    function setCaptureMode(active, durationMs) {
      if (captureTimer) {
        clearTimeout(captureTimer);
        captureTimer = null;
      }
      captureMode = active;
      root.classList.toggle('udrm-capturing', active);
      if (o.blackoutOnCapture) {
        root.classList.toggle('udrm-blackout', active);
      }
      if (active && durationMs) {
        captureTimer = setTimeout(() => {
          captureMode = false;
          root.classList.remove('udrm-capturing');
          root.classList.remove('udrm-blackout');
          captureTimer = null;
        }, durationMs);
      } else if (!active) {
        root.classList.remove('udrm-blackout');
      }
    }

    root.classList.add('udrm');
    root.textContent = '';
    const stage = document.createElement('div');
    stage.className = 'udrm-stage';
    root.appendChild(stage);

    if (o.kind === 'pages') {
      observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) {
          if (!entry.target.classList.contains('udrm-loaded') && !entry.target.classList.contains('udrm-failed')) {
            loadPage(entry.target);
          }
          activePages.add(entry.target);
        } else {
          activePages.delete(entry.target);
        }
      }), { rootMargin: '600px 0px' });

      for (let i = 0; i < o.pages; i++) {
        const page = document.createElement('div');
        page.className = 'udrm-page';
        page.dataset.index = i;
        const pageCanvas = document.createElement('canvas');
        pageCanvas.className = 'udrm-page-canvas';
        const wmCanvas = document.createElement('canvas');
        wmCanvas.className = 'udrm-wm-canvas';
        page.append(pageCanvas, wmCanvas);
        stage.appendChild(page);
        observer.observe(page);
      }
    } else if (o.kind === 'video') {
      const wrap = document.createElement('div');
      wrap.className = 'udrm-video';
      video = document.createElement('video');
      video.controls = true;
      video.disablePictureInPicture = true;
      video.disableRemotePlayback = true;
      video.setAttribute('controlsList', 'nodownload noplaybackrate noremoteplayback');
      video.preload = 'metadata';
      const source = document.createElement('source');
      source.src = o.videoUrl;
      if (o.videoType) source.type = o.videoType;
      video.appendChild(source);
      const overlay = document.createElement('canvas');
      overlay.className = 'udrm-overlay udrm-wm-canvas';
      wrap.append(video, overlay);
      stage.appendChild(wrap);
      videoOverlay = overlay;

      const updateSize = () => {
        const r = wrap.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
        overlay.width = Math.round(r.width * dpr);
        overlay.height = Math.round(r.height * dpr);
      };
      on(video, 'loadedmetadata', updateSize);
      on(window, 'resize', updateSize);
      updateSize();
    }

    async function loadPage(page) {
      const canvas = page.querySelector('.udrm-page-canvas') || page.querySelector('canvas');
      const wmCanvas = page.querySelector('.udrm-wm-canvas');
      try {
        const res = await fetch(o.pageUrl(Number(page.dataset.index)), { credentials: 'same-origin', cache: 'no-store' });
        if (!res.ok) { if (res.status === 404 || res.status === 410) end('expired'); return; }
        const bitmap = await createImageBitmap(await res.blob());
        if (ended) { bitmap.close(); return; }
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        if (wmCanvas) {
          wmCanvas.width = bitmap.width;
          wmCanvas.height = bitmap.height;
        }
        const ctx = canvas.getContext('2d');
        ctx.drawImage(bitmap, 0, 0);
        bitmap.close();
        page.classList.add('udrm-loaded');
      } catch (err) {
        page.classList.add('udrm-failed');
      }
    }

    // Dynamic watermark renderer.
    // alwaysWatermark=true: watermark is always visible (browser-mode shares).
    // alwaysWatermark=false (default): watermark only shows during detected capture signals.
    function renderWatermarks() {
      if (ended) return;
      const shouldDraw = o.alwaysWatermark || captureMode;

      if (!shouldDraw) {
        // Normal Viewing Mode (no alwaysWatermark): clear watermark layer.
        activePages.forEach(page => {
          const wmCanvas = page.querySelector('.udrm-wm-canvas');
          if (!wmCanvas || wmCanvas.width === 0 || wmCanvas.height === 0) return;
          const ctx = wmCanvas.getContext('2d');
          ctx.clearRect(0, 0, wmCanvas.width, wmCanvas.height);
        });
        if (videoOverlay && videoOverlay.width > 0 && videoOverlay.height > 0) {
          const vCtx = videoOverlay.getContext('2d');
          vCtx.clearRect(0, 0, videoOverlay.width, videoOverlay.height);
        }
      } else if (o.watermark) {
        // Capture mode or alwaysWatermark: draw full-contrast watermark.
        const currentStamp = stamp(o.watermark);
        const wmStyle = {
          fill: 'rgba(128, 128, 128, 0.45)',
          stroke: 'rgba(255, 255, 255, 0.50)'
        };

        activePages.forEach(page => {
          const wmCanvas = page.querySelector('.udrm-wm-canvas');
          if (!wmCanvas || wmCanvas.width === 0 || wmCanvas.height === 0) return;
          const ctx = wmCanvas.getContext('2d');
          ctx.clearRect(0, 0, wmCanvas.width, wmCanvas.height);
          drawWatermark(ctx, wmCanvas.width, wmCanvas.height, currentStamp, wmStyle);
        });

        if (videoOverlay && videoOverlay.width > 0 && videoOverlay.height > 0) {
          const vCtx = videoOverlay.getContext('2d');
          vCtx.clearRect(0, 0, videoOverlay.width, videoOverlay.height);
          drawWatermark(vCtx, videoOverlay.width, videoOverlay.height, currentStamp, wmStyle);
        }
      }

      animId = requestAnimationFrame(renderWatermarks);
    }

    animId = requestAnimationFrame(renderWatermarks);

    function end(reason) {
      if (ended) return;
      ended = true;
      if (animId) cancelAnimationFrame(animId);
      if (observer) observer.disconnect();
      timers.forEach(clearInterval);
      stage.querySelectorAll('canvas').forEach(c => { c.width = 0; c.height = 0; });
      if (video) { video.pause(); video.querySelectorAll('source').forEach(s => s.remove()); video.removeAttribute('src'); video.load(); }
      listeners.forEach(([t, type, fn, capture]) => t.removeEventListener(type, fn, capture));
      root.textContent = '';
      const note = document.createElement('p');
      note.className = 'udrm-ended';
      note.textContent = reason === 'revoked' ? 'Access to this content was revoked.' : 'This viewing session has ended.';
      root.appendChild(note);
      o.onEnd(reason);
    }

    // Copy routes & keystroke protections
    ['contextmenu', 'dragstart', 'selectstart'].forEach(type => on(root, type, stop));
    // Clear clipboard on copy/cut attempts
    ['copy', 'cut'].forEach(type => on(document, type, e => {
      e.preventDefault();
      if (navigator.clipboard) navigator.clipboard.writeText('').catch(() => {});
    }));

    let modifierActive = false;
    on(document, 'keydown', e => {
      const k = (e.key || '').toLowerCase(), mod = e.ctrlKey || e.metaKey;
      if (e.key === 'Control' || e.key === 'Alt' || e.key === 'Meta' || e.key === 'Shift') {
        modifierActive = true;
      }
      const blocked = (mod && ['p', 's', 'c', 'u', 'a'].includes(k)) || k === 'f12' || (mod && e.shiftKey && ['i', 'j', 'c'].includes(k));
      if (blocked) { e.preventDefault(); e.stopImmediatePropagation(); }

      // Detect screenshot shortcuts: PrintScreen, Win+Shift+S, Cmd+Shift+3/4/5
      if (k === 'printscreen' || e.code === 'PrintScreen' || (e.shiftKey && ['3', '4', '5', 's'].includes(k))) {
        setCaptureMode(true, 2000);
      }
    }, true);

    on(document, 'keyup', e => {
      const k = (e.key || '').toLowerCase();
      if (e.key === 'Control' || e.key === 'Alt' || e.key === 'Meta' || e.key === 'Shift') {
        modifierActive = false;
      }
      if (k === 'printscreen' || e.code === 'PrintScreen') {
        setCaptureMode(true, 2000);
        if (navigator.clipboard) navigator.clipboard.writeText('').catch(() => {});
      }
    });

    // Detect OS Snipping Tool: When Win+Shift+S or screenshot tool opens,
    // window blurs. If modifier keys were pressed or snipping tool steals focus,
    // briefly flash the watermark so the screen capture buffer gets it, then auto-hide.
    on(window, 'blur', () => {
      if (modifierActive) {
        setCaptureMode(true, 2500);
      } else {
        setCaptureMode(true, 800);
      }
    });
    on(window, 'focus', () => setCaptureMode(false));
    on(document, 'visibilitychange', () => {
      if (document.hidden) setCaptureMode(true, 800);
      else setCaptureMode(false);
    });
    on(window, 'beforeprint', () => setCaptureMode(true, 5000));
    on(window, 'afterprint', () => setCaptureMode(false));

    // Display capture hook: end the session when screen capture starts
    if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
      try {
        const origGetDisplayMedia = navigator.mediaDevices.getDisplayMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getDisplayMedia = async function (...args) {
          setCaptureMode(true, 15000);
          if (o.endOnCapture && o.statusUrl) {
            fetch(o.statusUrl.replace('/status', '/end'), {
              method: 'POST', credentials: 'same-origin'
            }).catch(() => {});
          }
          if (o.endOnCapture) end('capture-detected');
          return origGetDisplayMedia(...args);
        };
      } catch (err) {}
    }

    // Revocation and expiry
    if (o.statusUrl) {
      const poll = async () => {
        try {
          const res = await fetch(o.statusUrl, { credentials: 'same-origin', cache: 'no-store' });
          if (!res.ok) return end(res.status === 403 ? 'revoked' : 'expired');
          const body = await res.json();
          if (!body.active) end(body.reason || 'expired');
        } catch (err) { /* offline: keep showing until the server says otherwise */ }
      };
      timers.push(setInterval(poll, o.statusInterval * 1000));
    }

    return {
      destroy: () => end('closed'),
      get ended() { return ended; },
      setCaptureMode: setCaptureMode
    };
  }

  global.UniversalDRM = { mount: mount, version: '0.1.0' };
})(window);
