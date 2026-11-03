(() => {
  const query = new URLSearchParams(location.search);
  const uid = query.get('uid');
  const token = query.get('token');
  if (uid || token) history.replaceState(null, '', location.pathname);

  const requestForm = document.getElementById('request-form');
  const confirmForm = document.getElementById('confirm-form');
  const message = document.getElementById('reset-message');
  const confirming = Boolean(uid && token);
  if (uid || token) {
    requestForm.hidden = true;
    confirmForm.hidden = !confirming;
    document.getElementById('reset-title').textContent = confirming ? 'Choose a new password' : 'Invalid reset link';
    document.getElementById('reset-description').textContent = confirming
      ? 'Your reset link is valid for one hour.'
      : 'Request a new link from the sign-in page.';
    if (!confirming) requestForm.hidden = false;
  }

  async function submit(form, path, payload) {
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    message.textContent = '';
    try {
      const response = await fetch(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.password?.join?.(' ') || data.detail || 'The request could not be completed.');
      message.textContent = data.message;
      if (form === confirmForm) form.hidden = true;
    } catch (error) {
      message.textContent = error.message || 'The request could not be completed.';
    } finally {
      button.disabled = false;
    }
  }

  requestForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (requestForm.reportValidity()) {
      submit(requestForm, '/api/auth/password-reset/request/', {
        email: document.getElementById('reset-email').value.trim(),
      });
    }
  });
  confirmForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (confirmForm.reportValidity()) {
      submit(confirmForm, '/api/auth/password-reset/confirm/', {
        uid,
        token,
        password: document.getElementById('new-password').value,
      });
    }
  });
})();
