/*
 * UniversalDRM viewer. No dependencies, works under a strict CSP (script-src 'self').
 *
 *   const viewer = UniversalDRM.mount(element, {
 *     kind: 'pages',                     // or 'video'
 *     pages: 12, pageUrl: i => `/doc/page/${i}`,
 *     videoUrl: '/doc/video', videoType: 'video/mp4',
 *     watermark: 'Alice · #1a2b3c',      // drawn live on top, with the current time
 *     statusUrl: '/doc/status',          // polled; a non-2xx reply or {active:false} wipes the content
 *     statusInterval: 15,
 *     onEnd: reason => {}
 *   });
 *
 * A web page cannot stop the operating system's screenshot key or a camera. This viewer makes
 * the easy copy routes fail and makes every capture carry the watermark.
 */
(function (global) {
  'use strict';

  function drawWatermark(ctx, w, h, text) {
    const size = Math.max(12, Math.round(w / 45));
    ctx.save();
    ctx.font = `${size}px sans-serif`;
    ctx.fillStyle = 'rgba(128,128,128,0.22)';
    ctx.translate(w / 2, h / 2);
    ctx.rotate(-Math.PI / 6);
    const stepX = ctx.measureText(text).width + size * 4, stepY = size * 6, span = Math.hypot(w, h);
    for (let y = -span, row = 0; y < span; y += stepY, row++)
      for (let x = -span + (row % 2) * stepX / 2; x < span; x += stepX) ctx.fillText(text, x, y);
    ctx.restore();
  }

  function stamp(text) { return `${text} · ${new Date().toLocaleString()}`; }

  function mount(root, opts) {
    const o = Object.assign({ statusInterval: 15, watermark: '', onEnd: function () {} }, opts);
    const listeners = [], timers = [];
    let ended = false, observer = null, video = null;

    const on = (target, type, fn, capture) => { target.addEventListener(type, fn, capture); listeners.push([target, type, fn, capture]); };
    const stop = e => e.preventDefault();
    const shield = active => root.classList.toggle('udrm-shielded', active);

    root.classList.add('udrm');
    root.textContent = '';
    const stage = document.createElement('div');
    stage.className = 'udrm-stage';
    root.appendChild(stage);

    if (o.kind === 'pages') {
      observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) { observer.unobserve(entry.target); loadPage(entry.target); }
      }), { rootMargin: '600px 0px' });
      for (let i = 0; i < o.pages; i++) {
        const page = document.createElement('div');
        page.className = 'udrm-page';
        page.dataset.index = i;
        page.appendChild(document.createElement('canvas'));
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
      overlay.className = 'udrm-overlay';
      wrap.append(video, overlay);
      stage.appendChild(wrap);
      const redraw = () => {
        const r = wrap.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
        overlay.width = Math.round(r.width * dpr); overlay.height = Math.round(r.height * dpr);
        const ctx = overlay.getContext('2d');
        ctx.scale(dpr, dpr);
        drawWatermark(ctx, r.width, r.height, stamp(o.watermark));
      };
      on(video, 'loadedmetadata', redraw);
      on(window, 'resize', redraw);
      timers.push(setInterval(redraw, 30000));
      redraw();
    }

    async function loadPage(page) {
      const canvas = page.querySelector('canvas');
      try {
        const res = await fetch(o.pageUrl(Number(page.dataset.index)), { credentials: 'same-origin', cache: 'no-store' });
        if (!res.ok) { if (res.status === 404 || res.status === 410) end('expired'); return; }
        const bitmap = await createImageBitmap(await res.blob());
        if (ended) { bitmap.close(); return; }
        canvas.width = bitmap.width; canvas.height = bitmap.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(bitmap, 0, 0);
        bitmap.close();
        drawWatermark(ctx, canvas.width, canvas.height, stamp(o.watermark));
        page.classList.add('udrm-loaded');
      } catch (err) {
        page.classList.add('udrm-failed');
      }
    }

    function end(reason) {
      if (ended) return;
      ended = true;
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

    // Copy routes
    ['contextmenu', 'dragstart', 'selectstart', 'copy', 'cut'].forEach(type => on(root, type, stop));
    on(document, 'keydown', e => {
      const k = (e.key || '').toLowerCase(), mod = e.ctrlKey || e.metaKey;
      const blocked = (mod && ['p', 's', 'c', 'u', 'a'].includes(k)) || k === 'f12' || (mod && e.shiftKey && ['i', 'j', 'c'].includes(k));
      if (blocked) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
    on(document, 'keyup', e => {
      if (e.key === 'PrintScreen') { shield(true); if (navigator.clipboard) navigator.clipboard.writeText('').catch(() => {}); }
    });

    // Hide content whenever the page is not what the user is looking at
    on(window, 'blur', () => shield(true));
    on(window, 'focus', () => shield(false));
    on(document, 'visibilitychange', () => shield(document.hidden));
    on(window, 'beforeprint', () => shield(true));
    on(window, 'afterprint', () => shield(false));

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

    return { destroy: () => end('closed'), get ended() { return ended; } };
  }

  global.UniversalDRM = { mount: mount, version: '0.1.0' };
})(window);
