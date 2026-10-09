(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', async () => {
    const leader = location.pathname.includes('register-leader');
    const form = document.getElementById(leader ? 'leaderRegisterForm' : 'memberRegisterForm');
    if (!form) return;
    const banner = document.querySelector('.verification-hold-banner');
    try {
      const config = await fetch('/api/auth/config/').then(r => r.json());
      if (banner) banner.textContent = config.verificationRequired ? 'Verify your email to complete registration.' : 'Registration completes immediately; no email step is required.';
    } catch (_) {if (banner) banner.textContent = 'Register your account to continue.';}
    const params = new URLSearchParams(location.search);
    if (params.has('token') || params.has('uid')) {
      const token = params.get('token');
      const uid = params.get('uid');
      history.replaceState(null, '', location.pathname);
      form.style.display = 'none';
      const notice = document.createElement('p');
      notice.setAttribute('role', 'status'); notice.textContent = 'Verifying your email…';
      form.after(notice);
      try {
        const response = await fetch(`/api/auth/${leader ? 'verify-email' : 'verify-member-email'}/`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token, uid})});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Invalid or expired verification link.');
        notice.textContent = leader ? `Email verified. Your team code is ${data.teamCode}. You can now sign in.` : 'Email verified. Your team leader must approve your membership before you sign in.';
      } catch (error) {notice.textContent = error.message;}
    }
    const resend = document.createElement('button');
    resend.type = 'button'; resend.className = 'btn btn-outline'; resend.textContent = 'Resend verification email';
    const status = document.createElement('p'); status.setAttribute('role', 'status');
    const label = document.createElement('label');
    label.textContent = 'Email address for verification';
    const emailInput = document.createElement('input');
    emailInput.type = 'email'; emailInput.autocomplete = 'email';
    emailInput.className = 'form-input';
    label.append(emailInput);
    form.parentElement.append(label, resend, status);
    resend.addEventListener('click', async () => {
      const email = emailInput.value || document.getElementById(leader ? 'leaderEmail' : 'memberEmail').value;
      if (!email) {status.textContent = 'Enter your email address above first.'; return;}
      resend.disabled = true;
      try {
        const response = await fetch('/api/auth/resend-verification/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email})});
        const data = await response.json();
        status.textContent = response.ok ? data.message : data.error;
      } catch (_) {status.textContent = 'Unable to resend. Please retry.';}
      finally {resend.disabled = false;}
    });
  });
})();
