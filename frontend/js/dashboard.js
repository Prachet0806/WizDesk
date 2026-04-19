// dashboard.js — integrates with Django REST Framework backend
let currentUser = null;
let allTasks = [];

// ─── Helper: authenticated fetch ────────────────────────────────────────────
function authHeaders() {
    const token = localStorage.getItem('token');
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

async function apiFetch(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: { ...authHeaders(), ...(options.headers || {}) }
        });
        
        // Global Error Handling
        if (!response.ok && response.status >= 500) {
            if (typeof showMessage === 'function') {
                showMessage('A server error occurred (' + response.status + '). Please try again later.', 'error');
            }
        }
        
        // If 401, session expired — redirect to login
        if (response.status === 401) {
            localStorage.clear();
            window.location.href = 'index.html';
            return null;
        }
        return response;
    } catch (error) {
        if (typeof showMessage === 'function') {
            showMessage('A network error occurred. Please check your connection.', 'error');
        }
        throw error;
    }
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const userData = localStorage.getItem('user');
    if (!userData || !localStorage.getItem('token')) {
        window.location.href = 'index.html';
        return;
    }
    currentUser = JSON.parse(userData);
    initializeDashboard();
    loadTasks();
    setupEventListeners();
});

function initializeDashboard() {
    const nameEl = document.getElementById('userName');
    const roleEl = document.getElementById('userRole');
    const teamEl = document.getElementById('teamCode');
    if (nameEl) nameEl.textContent = `Welcome, ${currentUser.name}`;
    if (roleEl) roleEl.textContent = `Role: ${currentUser.role}`;
    if (teamEl) teamEl.textContent = `Team: ${currentUser.team_code || ''}`;

    if (currentUser.role === 'LEADER' || currentUser.role === 'leader') {
        const s = document.getElementById('leaderSection');
        if (s) s.style.display = 'block';
    } else {
        const s = document.getElementById('memberSection');
        if (s) s.style.display = 'block';
        loadUserSubtasks();
    }
}

function setupEventListeners() {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.clear();
            window.location.href = 'index.html';
        });
    }

    const createTaskModal = document.getElementById('createTaskModal');
    const createTaskBtn = document.getElementById('createTaskBtn');
    if (createTaskBtn && createTaskModal) {
        createTaskBtn.addEventListener('click', () => createTaskModal.style.display = 'block');
    }

    document.querySelectorAll('.close').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.modal').style.display = 'none';
        });
    });

    const addSubBtn = document.getElementById('addSubtaskBtn');
    if (addSubBtn) addSubBtn.addEventListener('click', addSubtaskField);

    const createForm = document.getElementById('createTaskForm');
    if (createForm) createForm.addEventListener('submit', createTask);

    window.addEventListener('click', (event) => {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    });
}

// ─── Task CRUD ────────────────────────────────────────────────────────────────
function addSubtaskField() {
    const container = document.getElementById('subtasksContainer');
    const div = document.createElement('div');
    div.className = 'subtask-input';
    div.innerHTML = `
        <input type="text" placeholder="Subtask title" class="subtask-title" required>
        <textarea placeholder="Subtask description" class="subtask-desc" rows="2"></textarea>
        <button type="button" class="remove-subtask">Remove</button>
    `;
    container.appendChild(div);
    div.querySelector('.remove-subtask').addEventListener('click', () => container.removeChild(div));
}

async function createTask(e) {
    e.preventDefault();
    const title = document.getElementById('taskTitle').value;
    const description = document.getElementById('taskDescription').value;
    const subtasks = Array.from(document.querySelectorAll('.subtask-input')).map(el => ({
        title: el.querySelector('.subtask-title').value,
        description: el.querySelector('.subtask-desc').value
    })).filter(s => s.title.trim());

    if (subtasks.length === 0) {
        showMessage('Please add at least one subtask', 'error');
        return;
    }

    // POST /api/tasks/ — custom create handles nested subtasks
    const response = await apiFetch(`${API_BASE}/tasks/`, {
        method: 'POST',
        body: JSON.stringify({ title, description, subtasks })
    });
    if (!response) return;
    const result = await response.json();

    if (response.ok) {
        showMessage('Task created successfully!');
        document.getElementById('createTaskModal').style.display = 'none';
        document.getElementById('createTaskForm').reset();
        document.getElementById('subtasksContainer').innerHTML = `
            <div class="subtask-input">
                <input type="text" placeholder="Subtask title" class="subtask-title">
                <textarea placeholder="Subtask description" class="subtask-desc" rows="2"></textarea>
                <button type="button" class="remove-subtask">Remove</button>
            </div>`;
        loadTasks();
    } else {
        showMessage(result.error || JSON.stringify(result), 'error');
    }
}

async function loadTasks() {
    // GET /api/tasks/ — filtered server-side to the user's team
    const response = await apiFetch(`${API_BASE}/tasks/`);
    if (!response) return;
    const tasks = await response.json();
    if (response.ok) {
        allTasks = Array.isArray(tasks) ? tasks : (tasks.results || []);
        displayTasks(allTasks);
        updateStats(allTasks);
    } else {
        showMessage('Failed to load tasks', 'error');
    }
}

function displayTasks(tasks) {
    const tasksList = document.getElementById('tasksList');
    if (!tasksList) return;
    if (tasks.length === 0) {
        tasksList.innerHTML = '<p class="no-tasks">No tasks created yet.</p>';
        return;
    }
    tasksList.innerHTML = tasks.map(task => `
        <div class="task-card" onclick="showTaskDetails('${task.id}')">
            <div class="task-header">
                <h3>${task.title}</h3>
                <span class="task-status ${task.status}">${task.status}</span>
            </div>
            <p class="task-description">${task.description || 'No description'}</p>
            <div class="task-progress">
                <div class="progress-bar">
                    <div class="progress" style="width: ${calculateProgress(task)}%"></div>
                </div>
                <span>${calculateProgress(task)}% Complete</span>
            </div>
            <div class="task-meta">
                <span>Created by: ${task.created_by_details?.name || '—'}</span>
                <span>Subtasks: ${(task.subtasks || []).length}</span>
            </div>
        </div>
    `).join('');
}

function calculateProgress(task) {
    const subtasks = task.subtasks || [];
    if (subtasks.length === 0) return 0;
    const done = subtasks.filter(st => st.status === 'completed').length;
    return Math.round((done / subtasks.length) * 100);
}

function updateStats(tasks) {
    const el = id => document.getElementById(id);
    if (el('totalTasks'))    el('totalTasks').textContent    = tasks.length;
    if (el('inProgressTasks')) el('inProgressTasks').textContent = tasks.filter(t =>
        (t.subtasks || []).some(s => s.progress === 'in_progress')).length;
    if (el('completedTasks')) el('completedTasks').textContent = tasks.filter(t =>
        (t.subtasks || []).length > 0 && (t.subtasks || []).every(s => s.status === 'completed')).length;
}

// ─── User subtasks (Member view) ─────────────────────────────────────────────
async function loadUserSubtasks() {
    // GET /api/subtasks/?mine=true
    const response = await apiFetch(`${API_BASE}/subtasks/?mine=true`);
    if (!response) return;
    const subtasks = await response.json();
    if (response.ok) {
        displayUserSubtasks(Array.isArray(subtasks) ? subtasks : (subtasks.results || []));
    }
}

function displayUserSubtasks(subtasks) {
    const list = document.getElementById('myTasksList');
    if (!list) return;
    if (subtasks.length === 0) {
        list.innerHTML = '<p class="no-tasks">No tasks assigned to you yet.</p>';
        return;
    }
    list.innerHTML = subtasks.map(st => `
        <div class="subtask-card ${st.status}">
            <div class="subtask-header">
                <h4>${st.title}</h4>
                <span class="subtask-status">${st.progress}</span>
            </div>
            <p>${st.description || 'No description'}</p>
            <div class="subtask-actions">
                <select onchange="updateSubtaskProgress('${st.id}', this.value)" class="progress-select">
                    <option value="not_started" ${st.progress==='not_started'?'selected':''}>Not Started</option>
                    <option value="in_progress" ${st.progress==='in_progress'?'selected':''}>In Progress</option>
                    <option value="testing" ${st.progress==='testing'?'selected':''}>Testing</option>
                    <option value="completed" ${st.progress==='completed'?'selected':''}>Completed</option>
                </select>
            </div>
        </div>
    `).join('');
}

async function updateSubtaskProgress(subtaskId, progress) {
    // POST /api/subtasks/<id>/update_progress/
    const response = await apiFetch(`${API_BASE}/subtasks/${subtaskId}/update_progress/`, {
        method: 'POST',
        body: JSON.stringify({ progress })
    });
    if (!response) return;
    const result = await response.json();
    if (response.ok) {
        showMessage('Progress updated!');
        loadTasks();
        loadUserSubtasks();
    } else {
        showMessage(result.error || 'Failed to update progress', 'error');
    }
}

// ─── Task details + Take subtask ─────────────────────────────────────────────
function showTaskDetails(taskId) {
    const task = allTasks.find(t => String(t.id) === String(taskId));
    if (!task) return;

    const titleEl = document.getElementById('taskDetailTitle');
    const descEl  = document.getElementById('taskDetailDescription');
    if (titleEl) titleEl.textContent = task.title;
    if (descEl)  descEl.textContent  = task.description || 'No description';

    const progress = calculateProgress(task);
    const bar  = document.getElementById('overallProgress');
    const text = document.getElementById('progressText');
    if (bar)  bar.style.width = `${progress}%`;
    if (text) text.textContent = `${progress}% Complete`;

    const listEl = document.getElementById('subtasksDetailsList');
    if (listEl) {
        const role = currentUser.role?.toUpperCase();
        listEl.innerHTML = (task.subtasks || []).map(st => `
            <div class="subtask-detail ${st.status}">
                <div class="subtask-info">
                    <h4>${st.title}</h4>
                    <p>${st.description || 'No description'}</p>
                    <div class="subtask-meta">
                        <span class="status">Status: ${st.status}</span>
                        <span class="progress">Progress: ${st.progress}</span>
                        <span class="assigned-to">Assigned to: ${st.assigned_to_details?.name || 'Not assigned'}</span>
                    </div>
                </div>
                ${(role === 'MEMBER' && !st.assigned_to) ?
                    `<button onclick="takeSubtask('${st.id}')" class="btn-primary">Take Task</button>` : ''}
            </div>
        `).join('');
    }

    const modal = document.getElementById('taskDetailsModal');
    if (modal) modal.style.display = 'block';
}

async function takeSubtask(subtaskId) {
    // POST /api/subtasks/<id>/take/
    const response = await apiFetch(`${API_BASE}/subtasks/${subtaskId}/take/`, { method: 'POST' });
    if (!response) return;
    const result = await response.json();
    if (response.ok) {
        showMessage('Task assigned to you!');
        const modal = document.getElementById('taskDetailsModal');
        if (modal) modal.style.display = 'none';
        loadTasks();
        loadUserSubtasks();
    } else {
        showMessage(result.error || 'Failed to take task', 'error');
    }
}

// ─── Task Management (Leader) ─────────────────────────────────────────────────
async function loadAllTasksForManagement() {
    const response = await apiFetch(`${API_BASE}/tasks/`);
    if (!response) return;
    const data = await response.json();
    displayTasksForManagement(Array.isArray(data) ? data : (data.results || []));
}

function displayTasksForManagement(tasks) {
    const container = document.getElementById('allTasksManagement');
    if (!container) return;
    if (tasks.length === 0) {
        container.innerHTML = `<div class="empty-state"><div class="icon">📝</div><h3>No Tasks Created</h3><p>Create your first task to get started</p></div>`;
        return;
    }
    container.innerHTML = tasks.map(task => `
        <div class="task-card">
            <div class="task-header">
                <div>
                    <div class="task-title">${task.title}</div>
                    <div class="task-description">${task.description || 'No description'}</div>
                </div>
                <span class="task-status">${task.status}</span>
            </div>
            <div class="progress-section">
                <div class="progress-info"><span>Progress</span><span>${calculateProgress(task)}%</span></div>
                <div class="progress-bar"><div class="progress" style="width:${calculateProgress(task)}%"></div></div>
            </div>
            <div class="task-meta">
                <span style="color:#666;font-size:.9rem">${(task.subtasks||[]).length} subtasks • Created by ${task.created_by_details?.name || '—'}</span>
                <div class="task-actions">
                    <button class="btn btn-sm btn-primary" onclick="manageTask('${task.id}')">Manage</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteTask('${task.id}')">Delete</button>
                </div>
            </div>
        </div>
    `).join('');
}

async function manageTask(taskId) {
    const response = await apiFetch(`${API_BASE}/tasks/${taskId}/`);
    if (!response) return;
    const task = await response.json();
    const content = document.getElementById('manageTaskContent');
    if (!content) return;
    content.innerHTML = `
        <h3>${task.title}</h3><p>${task.description || 'No description'}</p>
        <div class="subtasks-section" style="margin-top:20px">
            <h4>Subtasks</h4>
            ${(task.subtasks || []).map(st => `
                <div class="subtask-item" style="display:flex;justify-content:space-between;align-items:center;padding:15px;background:#f8f9fa;border-radius:8px;margin-bottom:10px">
                    <div>
                        <strong>${st.title}</strong>
                        <div style="font-size:.9rem;color:#666">Status: ${st.status} | Assigned: ${st.assigned_to_details?.name || 'Not assigned'}</div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="deleteSubtask('${st.id}')">Remove</button>
                </div>`).join('')}
        </div>
        <div style="margin-top:20px;display:flex;gap:10px">
            <button class="btn btn-danger" onclick="deleteTask('${task.id}')" style="flex:1">Delete Task</button>
            <button class="btn btn-outline" onclick="closeModal('manageTaskModal')" style="flex:1">Close</button>
        </div>`;
    showModal('manageTaskModal');
}

async function deleteTask(taskId) {
    if (!confirm('Delete this task and all its subtasks?')) return;
    const response = await apiFetch(`${API_BASE}/tasks/${taskId}/`, { method: 'DELETE' });
    if (!response) return;
    if (response.status === 204 || response.ok) {
        showMessage('Task deleted!', 'success');
        closeModal('manageTaskModal');
        loadTasks();
        loadAllTasksForManagement();
    } else {
        const r = await response.json();
        showMessage(r.error || 'Failed to delete task', 'error');
    }
}

async function deleteSubtask(subtaskId) {
    if (!confirm('Delete this subtask?')) return;
    const response = await apiFetch(`${API_BASE}/subtasks/${subtaskId}/`, { method: 'DELETE' });
    if (!response) return;
    if (response.status === 204 || response.ok) {
        showMessage('Subtask deleted!', 'success');
        closeModal('manageTaskModal');
        loadTasks();
    } else {
        const r = await response.json();
        showMessage(r.error || 'Failed to delete subtask', 'error');
    }
}

// ─── Member Management (Leader) ───────────────────────────────────────────────
async function loadAllTeamMembers() {
    // GET /api/auth/team/members/
    const response = await apiFetch(`${API_BASE}/auth/team/members/`);
    if (!response) return;
    const data = await response.json();
    displayAllTeamMembers(Array.isArray(data) ? data : (data.results || []));
}

function displayAllTeamMembers(members) {
    const container = document.getElementById('membersList');
    if (!container) return;
    if (members.length === 0) {
        container.innerHTML = `<div class="empty-state"><div class="icon">👥</div><h3>No Team Members</h3><p>Team members will appear here when they join</p></div>`;
        return;
    }
    container.innerHTML = members.map(m => `
        <div class="member-card">
            <div class="member-avatar">${m.name.charAt(0).toUpperCase()}</div>
            <div class="member-name">${m.name}</div>
            <div class="member-email">${m.email}</div>
            <div class="member-role ${m.role.toLowerCase()}">${m.role}</div>
            ${(m.role === 'MEMBER' || m.role === 'member') ? `
            <div class="member-actions">
                <button class="btn btn-sm btn-danger" onclick="deleteMember('${m.id}', '${m.name}')">Remove</button>
            </div>` : ''}
        </div>
    `).join('');
}

async function deleteMember(memberId, memberName) {
    if (!confirm(`Remove ${memberName} from the team?`)) return;
    // DELETE /api/auth/team/member/<id>/
    const response = await apiFetch(`${API_BASE}/auth/team/member/${memberId}/`, { method: 'DELETE' });
    if (!response) return;
    if (response.ok) {
        showMessage('Member removed!', 'success');
        loadAllTeamMembers();
    } else {
        const r = await response.json();
        showMessage(r.error || 'Failed to remove member', 'error');
    }
}

// ─── Task filtering (by status tab) ──────────────────────────────────────────
async function loadTasksByStatus(statusFilter) {
    const response = await apiFetch(`${API_BASE}/tasks/?status=${statusFilter}`);
    if (!response) return;
    const data = await response.json();
    const tasks = Array.isArray(data) ? data : (data.results || []);
    if (statusFilter === 'active') displayActiveTasks(tasks);
    else displayCompletedTasks(tasks);
}

function displayActiveTasks(tasks) {
    const container = document.getElementById('activeTasksList');
    if (container) displayFilteredTasks(container, tasks, 'active');
}

function displayCompletedTasks(tasks) {
    const container = document.getElementById('completedTasksList');
    if (container) displayFilteredTasks(container, tasks, 'completed');
}

function displayFilteredTasks(container, tasks, type) {
    if (tasks.length === 0) {
        container.innerHTML = `<div class="empty-state"><div class="icon">${type==='active'?'📝':'✅'}</div><h3>No ${type} Tasks</h3></div>`;
        return;
    }
    container.innerHTML = tasks.map(task => `
        <div class="task-card">
            <div class="task-header">
                <div><div class="task-title">${task.title}</div><div class="task-description">${task.description||''}</div></div>
                <span class="task-status">${task.status}</span>
            </div>
            <div class="task-meta">
                <button class="btn btn-sm btn-primary" onclick="manageTask('${task.id}')">View Details</button>
            </div>
        </div>
    `).join('');
}

// ─── Tab switching ────────────────────────────────────────────────────────────
function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));

    const tabEl = document.getElementById(tabId);
    if (tabEl) tabEl.style.display = 'block';
    const navEl = document.querySelector(`[data-tab="${tabId}"]`);
    if (navEl) navEl.classList.add('active');

    switch (tabId) {
        case 'tasks':          loadAllTasksForManagement(); break;
        case 'members':        loadAllTeamMembers(); break;
        case 'active-tasks':   loadTasksByStatus('active'); break;
        case 'completed-tasks':loadTasksByStatus('completed'); break;
    }
}

// ─── Modal helpers ────────────────────────────────────────────────────────────
function showModal(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'block';
}
function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
}
