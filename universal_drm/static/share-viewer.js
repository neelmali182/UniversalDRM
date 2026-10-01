(function () {
  'use strict';

  const root = document.getElementById('share-viewer');
  const emailForm = document.getElementById('email-form');
  const otpForm = document.getElementById('otp-form');
  const status = document.getElementById('share-status');
  const shareToken = root.dataset.shareToken;
  let verificationId = null;

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'The request failed.');
    return result;
  }

  emailForm.addEventListener('submit', async event => {
    event.preventDefault();
    status.textContent = 'Checking share and sending a verification code…';
    try {
      const result = await postJson('/v1/viewer/verify/start', {
        share_token: shareToken,
        email: new FormData(emailForm).get('email')
      });
      verificationId = result.verification_id;
      emailForm.hidden = true;
      otpForm.hidden = false;
      const developmentOtp = document.querySelector('#otp-form input[name="otp"]');
      if (result.development_otp) {
        developmentOtp.value = result.development_otp;
        status.textContent = `Development verification code: ${result.development_otp}`;
      } else {
        status.textContent = 'Check your email for the verification code.';
      }
    } catch (error) {
      status.textContent = error.message;
    }
  });

  otpForm.addEventListener('submit', async event => {
    event.preventDefault();
    status.textContent = 'Verifying…';
    try {
      await postJson('/v1/viewer/verify/confirm', {
        verification_id: verificationId,
        otp: new FormData(otpForm).get('otp')
      });
      const session = await postJson('/v1/viewer/sessions', {
        share_token: shareToken,
        verification_id: verificationId
      });
      const contentResponse = await fetch(`/v1/viewer/sessions/${encodeURIComponent(session.session_id)}/content`, {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      const content = await contentResponse.json();
      if (!contentResponse.ok) throw new Error(content.detail || 'The document could not be opened.');
      emailForm.remove();
      otpForm.remove();
      status.textContent = '';
      window.UniversalDRM.mount(document.getElementById('viewer'), {
        kind: content.kind,
        pages: content.pages,
        pageUrl: index => `/v1/viewer/sessions/${encodeURIComponent(session.session_id)}/pages/${index}`,
        watermark: content.watermark_visible ? session.watermark_text : '',
        statusUrl: `/v1/viewer/sessions/${encodeURIComponent(session.session_id)}/heartbeat`,
        statusInterval: 15,
        blackoutOnCapture: false
      });
    } catch (error) {
      status.textContent = error.message;
    }
  });
})();