// Global constants
const API_BASE = 'http://localhost:8000/api';
const SOCKET_URL = 'http://localhost:8000';

// Common utility functions
const showMessage = (message, type = 'success') => {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.textContent = message;
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 25px;
        background: ${type === 'success' ? 'linear-gradient(135deg, #28a745, #20c997)' : 'linear-gradient(135deg, #dc3545, #e83e8c)'};
        color: white;
        border-radius: 10px;
        z-index: 10000;
        font-weight: 500;
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    `;
    document.body.appendChild(messageDiv);
    setTimeout(() => messageDiv.remove(), 4000);
};

// Modal functionality
const setupModals = () => {
    const modal = document.getElementById('memberRegisterModal');
    const showBtn = document.getElementById('showMemberRegister');
    const closeBtn = document.querySelector('.close');

    if (showBtn && modal) {
        showBtn.onclick = (e) => {
            e.preventDefault();
            modal.style.display = 'block';
        };
    }

    if (closeBtn && modal) {
        closeBtn.onclick = () => modal.style.display = 'none';
    }

    window.onclick = (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    };
};

// Form handling utilities
const getFormData = (form) => {
    const inputs = form.querySelectorAll('input');
    const data = {};
    inputs.forEach(input => {
        const fieldName = input.id || input.getAttribute('name') || input.placeholder.toLowerCase().replace(/\s+/g, '_');
        data[fieldName] = input.value;
    });
    return data;
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    setupModals();
    console.log('WizDesk Frontend Loaded');
});
