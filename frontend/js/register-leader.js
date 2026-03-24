// register-leader.js — integrates with Django REST Framework backend
document.addEventListener('DOMContentLoaded', () => {
    const leaderRegisterForm = document.getElementById('leaderRegisterForm');
    const successMessage = document.getElementById('successMessage');

    if (leaderRegisterForm) {
        leaderRegisterForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                name: document.getElementById('leaderName').value,
                email: document.getElementById('leaderEmail').value,
                password: document.getElementById('leaderPassword').value,
                team_name: document.getElementById('teamName').value,  // Django field name
            };

            try {
                const response = await fetch(`${API_BASE}/auth/register-leader/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (response.ok) {
                    const teamCodeEl = document.getElementById('generatedTeamCode');
                    if (teamCodeEl) teamCodeEl.textContent = result.team_code || result.teamCode;
                    leaderRegisterForm.style.display = 'none';
                    if (successMessage) successMessage.style.display = 'block';
                } else {
                    showMessage(result.error || JSON.stringify(result), 'error');
                }
            } catch (err) {
                showMessage('Registration failed. Please try again.', 'error');
            }
        });
    }
});
