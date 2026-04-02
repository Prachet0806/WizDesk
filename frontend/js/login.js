// login.js — integrates with Django REST Framework backend
document.addEventListener('DOMContentLoaded', () => {
    const leaderLoginForm = document.getElementById('leaderLoginForm');
    const memberLoginForm = document.getElementById('memberLoginForm');
    const memberRegisterForm = document.getElementById('memberRegisterForm');

    async function doLogin(email, password) {
        const response = await fetch(`${API_BASE}/auth/login/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const result = await response.json();
        if (response.ok) {
            // Store token and user data – always use Bearer token for future requests
            localStorage.setItem('token', result.token);
            localStorage.setItem('user', JSON.stringify(result.user));
            showMessage('Login successful! Redirecting...');
            setTimeout(() => { window.location.href = 'dashboard.html'; }, 1000);
        } else {
            showMessage(result.error || 'Login failed.', 'error');
        }
    }

    // Leader Login
    if (leaderLoginForm) {
        leaderLoginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = leaderLoginForm.querySelector('input[type="email"]')?.value
                        || leaderLoginForm.querySelectorAll('input')[0].value;
            const password = leaderLoginForm.querySelector('input[type="password"]')?.value
                           || leaderLoginForm.querySelectorAll('input')[1].value;
            try { await doLogin(email, password); }
            catch (err) { showMessage('Login failed. Please try again.', 'error'); }
        });
    }

    // Member Login
    if (memberLoginForm) {
        memberLoginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const inputs = memberLoginForm.querySelectorAll('input');
            try { await doLogin(inputs[0].value, inputs[1].value); }
            catch (err) { showMessage('Login failed. Please try again.', 'error'); }
        });
    }

    // Member Registration
    if (memberRegisterForm) {
        memberRegisterForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const inputs = memberRegisterForm.querySelectorAll('input');
            const data = {
                name: inputs[0].value,
                email: inputs[1].value,
                password: inputs[2].value,
                team_code: inputs[3].value,   // Django expects snake_case
                teamCode: inputs[3].value,     // also send camelCase for safety
            };
            try {
                const response = await fetch(`${API_BASE}/auth/send-member-verification/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (response.ok) {
                    showMessage('Registration successful! Please wait for leader approval.');
                    document.getElementById('memberRegisterModal').style.display = 'none';
                    memberRegisterForm.reset();
                } else {
                    showMessage(result.error || JSON.stringify(result), 'error');
                }
            } catch (err) {
                showMessage('Registration failed. Please try again.', 'error');
            }
        });
    }
});
