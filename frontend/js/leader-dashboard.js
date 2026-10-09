
        const API_BASE = '/api';

        // Theme — single authority is WizDeskTheme (js/theme.js).
        // body.dark-theme is kept in sync only so legacy component CSS still responds.
        const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>';
        const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

        // XSS prevention: escape HTML special chars for safe interpolation
        // NOTE: this is for HTML *text/attribute* context only. Never
        // interpolate user data into inline JS strings (onclick="...").
        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;')
                .replace(/`/g, '&#x60;');
        }
        // Attribute-context escaping (quotes + angle brackets). Use for
        // data-* attributes that carry user-controlled strings.
        function escapeAttr(value) {
            return escapeHtml(value).replace(/\//g, '&#x2F;');
        }
        function syncThemeChrome() {
            const isDark = window.WizDeskTheme ? window.WizDeskTheme.isDark() : document.documentElement.getAttribute('data-theme') === 'dark';
            document.body.classList.toggle('dark-theme', isDark);
            try { localStorage.setItem('theme', isDark ? 'dark' : 'light'); } catch (e) {}
            const btn = document.getElementById('themeToggle');
            if (btn) btn.innerHTML = isDark ? ICON_SUN : ICON_MOON;
        }
        function setThemeIcon(isDark) {
            const btn = document.getElementById('themeToggle');
            if (btn) btn.innerHTML = isDark ? ICON_SUN : ICON_MOON;
        }
        function initTheme() {
            // theme.js auto-applies stored/system theme on load; just sync chrome
            syncThemeChrome();
            document.addEventListener('themechange', syncThemeChrome);
            if (window.WizDeskTheme) window.WizDeskTheme.onChange(syncThemeChrome);
        }

        function toggleTheme() {
            if (window.WizDeskTheme) { window.WizDeskTheme.toggle(); return; }
            const isDark = document.body.classList.toggle('dark-theme');
            document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
            try { localStorage.setItem('theme', isDark ? 'dark' : 'light'); } catch (e) {}
            setThemeIcon(isDark);
        }

        initTheme();

        // Sidebar collapse (desktop) / drawer (mobile) — persisted
        function toggleSidebar() {
            const isMobile = window.matchMedia('(max-width: 1023px)').matches;
            if (isMobile) {
                document.body.classList.toggle('sidebar-open');
            } else {
                const collapsed = document.body.classList.toggle('sidebar-collapsed');
                try { localStorage.setItem('wizdesk-sidebar', collapsed ? 'collapsed' : 'open'); } catch (e) {}
            }
        }
        (function initSidebar() {
            try {
                if (localStorage.getItem('wizdesk-sidebar') === 'collapsed' && !window.matchMedia('(max-width: 1023px)').matches) {
                    document.body.classList.add('sidebar-collapsed');
                }
            } catch (e) {}
            const scrim = document.createElement('div');
            scrim.className = 'sidebar-scrim';
            scrim.onclick = () => document.body.classList.remove('sidebar-open');
            document.body.appendChild(scrim);
        })();

        let editingTaskSnapshot = null;
        let currentUser = null;
        let teamMembers = [];
        let allTasks = [];
        let pendingRequests = [];
        let rejectedMembers = [];
        let memberPerformanceData = [];
        let selectedMembers = [];
        let lastCompletedTaskIds = new Set();
        let lastActiveTaskIds = new Set();
        let lastSubtaskStatuses = {};
        let isInitialLoad = true;

        // Create notification container
        const notifContainer = document.createElement('div');
        notifContainer.className = 'notification-container';
        document.body.appendChild(notifContainer);

        function showTaskNotification(title, message) {
            const notif = document.createElement('div');
            notif.className = `task-notification`;

            notif.innerHTML = `
                <div class="notif-icon"><i data-lucide="check-circle-2"></i></div>
                <div class="notif-content">
                    <span class="notif-title">${escapeHtml(title)}</span>
                    <span class="notif-msg">${escapeHtml(message)}</span>
                </div>
            `;
            if (window.WizDeskIcons) window.WizDeskIcons.init();

            notif.onclick = () => {
                notif.classList.add('closing');
                setTimeout(() => notif.remove(), 500);
            };

            notifContainer.appendChild(notif);

            // Auto-remove after 8 seconds
            setTimeout(() => {
                if (notif.parentElement) {
                    notif.classList.add('closing');
                    setTimeout(() => notif.remove(), 500);
                }
            }, 8000);
        }

        function checkTaskUpdates(tasks) {
            tasks.forEach(task => {
                if (task.subtasks) {
                    task.subtasks.forEach(subtask => {
                        const oldStatus = lastSubtaskStatuses[subtask.id];
                        
                        // Check for ANY status change
                        if (oldStatus && oldStatus !== subtask.status) {
                            if (!isInitialLoad) {
                                const memberName = subtask.assigned_to_details?.name || subtask.assigned_to_name || 'A team member';
                                const title = 'Task Status Update';
                                const msg = `${escapeHtml(memberName)} updated "${escapeHtml(subtask.title)}" to ${escapeHtml(subtask.status.replace('_', ' '))}.`;
                                showToastNotification(title, msg, 'status');
                            }
                        }
                        
                        // Legacy completion/active checks for sidebar badges
                        const sStatus = subtask.status;
                        const sProgress = subtask.progress;
                        
                        if (sStatus === 'completed' || sProgress === 'completed') {
                            if (!lastCompletedTaskIds.has(subtask.id)) {
                                if (!isInitialLoad && document.getElementById('completed-tasks').style.display !== 'block') {
                                    document.getElementById('completedTasksBadge').style.display = 'inline-block';
                                }
                                lastCompletedTaskIds.add(subtask.id);
                            }
                        }
                        
                        lastSubtaskStatuses[subtask.id] = subtask.status;
                    });
                }
            });
        }

        // AUTHENTICATION CHECK
        document.addEventListener('DOMContentLoaded', async function() {
            try {
                currentUser = await WizDeskAPI.initialize('leader');
                if (!currentUser) return;
            initializeDashboard();
            await loadTeamData();
            WizDeskAPI.poll(async () => {
                await loadTeamData();
                if (document.getElementById('performance').style.display !== 'none') await loadPerformanceData(true);
            });
            } catch (error) {showMessage(error.message, 'error');}
        });

        // Utility functions
        function showMessage(message, type = 'success') {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;
            messageDiv.textContent = message;
            document.body.appendChild(messageDiv);
            setTimeout(() => messageDiv.remove(), 4000);
        }

        function closeModal(modalId) {
            document.getElementById(modalId).style.display = 'none';
        }

        function showModal(modalId) {
            document.getElementById(modalId).style.display = 'flex';
        }

        function showConfirmModal(title, message, onConfirm) {
            document.getElementById('confirmTitle').textContent = title;
            document.getElementById('confirmMessage').textContent = message;
            const proceedBtn = document.getElementById('confirmProceedBtn');
            
            // Clone button to remove old listeners
            const newBtn = proceedBtn.cloneNode(true);
            proceedBtn.parentNode.replaceChild(newBtn, proceedBtn);
            
            newBtn.onclick = () => {
                onConfirm();
                closeModal('confirmModal');
            };
            
            showModal('confirmModal');
        }

        function showTab(tabId) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.style.display = 'none';
            });
            document.querySelectorAll('.sidebar-item').forEach(li => {
                li.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabId).style.display = 'block';
            updateYellowDots();
            document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

            // Hide notification badge if present
            if (tabId === 'active-tasks') {
                document.getElementById('activeTasksBadge').style.display = 'none';
            } else if (tabId === 'completed-tasks') {
                document.getElementById('completedTasksBadge').style.display = 'none';
            }
            
            // Load specific data for tabs
            switch(tabId) {
                case 'approval-requests':
                    loadApprovalRequests();
                    break;
                case 'tasks':
                    loadAllTasksForManagement();
                    break;
                case 'members':
                    loadAllTeamMembers();
                    break;
                case 'rejected-members':
                    loadRejectedMembers();
                    break;
                case 'active-tasks':
                    loadTasksByStatus('active');
                    break;
                case 'completed-tasks':
                    loadTasksByStatus('completed');
                    break;
                case 'performance':
                    loadPerformanceData();
                    break;
            }
        }

        function initializeDashboard() {
            document.getElementById('userName').textContent = currentUser.name;
            const sidebarName = document.getElementById('sidebarUserName');
            if (sidebarName) sidebarName.textContent = currentUser.name;
            const sidebarAvatar = document.getElementById('sidebarAvatar');
            if (sidebarAvatar && currentUser.name) sidebarAvatar.textContent = currentUser.name.charAt(0).toUpperCase();
            document.getElementById('teamCodeDisplay').textContent = currentUser.team_code;

            // Navigation (V2 sidebar-item anchors)
            document.querySelectorAll('.sidebar-item').forEach(item => {
                item.addEventListener('click', function(e) {
                    e.preventDefault();
                    const tabId = this.getAttribute('data-tab');
                    showTab(tabId);
                });
            });

          // Logout
document.getElementById('logoutBtn').addEventListener('click', function() {
    showLogoutConfirmation();
});

function showLogoutConfirmation() {
    // Create confirmation modal
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.display = 'flex';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 400px;">
            <div class="modal-header">
                <h3>Confirm Logout</h3>
            </div>
            <div class="modal-body">
                <p>Are you sure you want to logout?</p>
            </div>
            <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                <button class="btn btn-outline" id="cancelLogout">Cancel</button>
                <button class="btn btn-danger" id="confirmLogout">Logout</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add event listeners
    document.getElementById('cancelLogout').addEventListener('click', function() {
        document.body.removeChild(modal);
    });
    
    document.getElementById('confirmLogout').addEventListener('click', function() {
        WizDeskAPI.logout().catch(console.error);
    });
    
    // Close modal when clicking outside
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            document.body.removeChild(modal);
        }
    });
}

            // Performance search functionality
            document.getElementById('performanceSearch').addEventListener('input', function() {
                filterPerformanceData();
            });

            // Performance filter functionality
            document.querySelectorAll('.performance-filters .performance-filter-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.performance-filters .performance-filter-btn').forEach(b => {
                        b.classList.remove('active');
                    });
                    this.classList.add('active');
                    filterPerformanceData();
                });
            });
        }

        async function loadTeamData() {
            try {
                // Load team members (only approved)
                const membersResponse = await fetch(`${API_BASE}/auth/team/${currentUser.team_code}/all-members/`);
                if (membersResponse.ok) {
                    teamMembers = await membersResponse.json();
                } else {
                    console.error('Failed to load team members');
                    teamMembers = [];
                }
                
                // Load pending requests
                await loadPendingRequests();
                
                // Load rejected members
                await loadRejectedMembers();
                
                // Load tasks
                await loadTasks();
                
                // Load transfer requests
                await loadTransferRequests();
                
                updateDashboardStats();
                
            } catch (error) {
                console.error('Error loading team data:', error);
                showMessage('Failed to load team data', 'error');
            }
        }

        async function loadPendingRequests() {
            try {
                const response = await fetch(`${API_BASE}/auth/team/${currentUser.team_code}/pending-requests/`);
                if (response.ok) {
                    const data = await response.json();
                    
                    // Check for new requests
                    const hasNew = data.some(r => !pendingRequests.find(pr => pr.id === r.id));
                    if (!isInitialLoad && hasNew) {
                        const newRequests = data.filter(r => !pendingRequests.find(pr => pr.id === r.id));
                        newRequests.forEach(r => {
                            showToastNotification('New Member Request', `${r.name} requested to join.`, 'request');
                        });
                    }
                    
                    pendingRequests = data;
                    updatePendingRequestsBadge();
                    updateYellowDots();
                } else {
                    console.error('Failed to load pending requests');
                    pendingRequests = [];
                }
            } catch (error) {
                console.error('Error loading pending requests:', error);
                pendingRequests = [];
            }
        }

        async function loadRejectedMembers() {
            try {
                const response = await fetch(`${API_BASE}/auth/team/${currentUser.team_code}/rejected-members/`);
                if (response.ok) {
                    rejectedMembers = await response.json();
                    updateRejectedMembersDisplay();
                } else {
                    console.error('Failed to load rejected members');
                    rejectedMembers = [];
                    updateRejectedMembersDisplay();
                }
            } catch (error) {
                console.error('Error loading rejected members:', error);
                rejectedMembers = [];
                updateRejectedMembersDisplay();
            }
        }

        function updatePendingRequestsBadge() {
            const badge = document.getElementById('pendingRequestsBadge');
            const stat = document.getElementById('pendingRequests');
            
            if (pendingRequests.length > 0) {
                badge.textContent = pendingRequests.length;
                badge.style.display = 'block';
                stat.textContent = pendingRequests.length;
            } else {
                badge.style.display = 'none';
                stat.textContent = '0';
            }
        }

        async function loadTasks() {
            try {
                const response = await fetch(`${API_BASE}/tasks/team/${currentUser.team_code}/`);
                if (response.ok) {
                    let data = await response.json();
                    allTasks = data.results || data;
                    checkTaskUpdates(allTasks);
                    isInitialLoad = false;
                    displayRecentTasks();
                    updateYellowDots();
                } else {
                    console.error('Failed to load tasks');
                    allTasks = [];
                }
            } catch (error) {
                console.error('Error loading tasks:', error);
                showMessage('Failed to load tasks', 'error');
                allTasks = [];
            }
        }

        function displayRecentTasks() {
            const container = document.getElementById('recentTasksList');
            
            if (allTasks.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="inbox"></i></div>
                        <h3>No Tasks Yet</h3>
                        <p>Create your first task to get started</p>
                        <button class="btn btn-primary" onclick="showCreateTaskModal()" style="margin-top: 15px;">
                            Create First Task
                        </button>
                    </div>
                `;
                return;
            }

            const recentTasks = allTasks.slice(0, 5);
            container.innerHTML = recentTasks.map(task => `
                <div class="task-card" onclick="showTaskDetail('${task.id}')" style="cursor: pointer;">
                    <div class="task-header">
                        <div>
                            <div class="task-title">${escapeHtml(task.title)}</div>
                            <div class="task-description">${escapeHtml(task.description || 'No description provided')}</div>
                        </div>
                        <span class="status-badge ${getTaskStatusClass(task)}">${getTaskStatusText(task)}</span>
                    </div>
                    <div class="progress-section">
                        <div class="progress-info">
                            <span>Progress</span>
                            <span>${calculateProgress(task)}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress" style="width: ${calculateProgress(task)}%"></div>
                        </div>
                    </div>
                    <div class="task-meta">
                        <div>
                            <span style="color: #666; font-size: 0.9rem;">
                                ${task.subtasks.length} subtasks • Created by ${task.created_by_name}
                            </span>
                        </div>
                        <div class="task-actions">
                            <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); editTask('${task.id}')">Edit</button>
                            <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); deleteTask('${task.id}')">Delete</button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function calculateProgress(task) {
            if (task.subtasks.length === 0) return 0;
            const completed = task.subtasks.filter(st => st.status === 'completed').length;
            return Math.round((completed / task.subtasks.length) * 100);
        }

        function updateDashboardStats() {
            document.getElementById('totalTasks').textContent = allTasks.length;
            
            const activeTasks = allTasks.filter(task => 
                task.subtasks.some(subtask => subtask.status !== 'completed')
            ).length;
            document.getElementById('activeTasks').textContent = activeTasks;
            
            document.getElementById('teamMembers').textContent = teamMembers.length;
            
            const completedTasks = allTasks.filter(task => 
                task.subtasks.length > 0 && task.subtasks.every(st => st.status === 'completed')
            ).length;
            document.getElementById('completedTasks').textContent = completedTasks;
        }

        // LIVE TASK DELETION FUNCTIONS
        async function deleteTask(taskId) {
            if (!confirm('Are you sure you want to delete this task? This will also delete all subtasks.')) {
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/tasks/${taskId}/`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ userId: currentUser.id })
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Task deleted successfully!', 'success');
                    // Remove task from local array immediately
                    allTasks = allTasks.filter(task => task.id !== taskId);
                    // Update all displays immediately
                    updateTaskDisplays();
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error deleting task:', error);
                showMessage('Failed to delete task', 'error');
            }
        }

        async function deleteTaskFromEdit() {
            const taskId = document.getElementById('editTaskId').value;
            
            if (!confirm('Are you sure you want to delete this task? This will also delete all subtasks.')) {
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/tasks/${taskId}/`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ userId: currentUser.id })
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Task deleted successfully!', 'success');
                    closeModal('editTaskModal');
                    // Remove task from local array immediately
                    allTasks = allTasks.filter(task => task.id !== taskId);
                    // Update all displays immediately
                    updateTaskDisplays();
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error deleting task:', error);
                showMessage('Failed to delete task', 'error');
            }
        }

        function updateTaskDisplays() {
            // Update dashboard stats
            updateDashboardStats();
            
            // Update recent tasks
            displayRecentTasks();
            
            // Update task management view if it's currently active
            const tasksTab = document.getElementById('tasks');
            if (tasksTab.style.display !== 'none') {
                displayTasksForManagement(allTasks);
            }
            
            // Update active tasks view if it's currently active
            const activeTasksTab = document.getElementById('active-tasks');
            if (activeTasksTab.style.display !== 'none') {
                const activeTasks = allTasks.filter(task => 
                    task.subtasks.some(subtask => subtask.status !== 'completed')
                );
                displayFilteredTasks(document.getElementById('activeTasksList'), activeTasks, 'active');
            }
            
            // Update completed tasks view if it's currently active
            const completedTasksTab = document.getElementById('completed-tasks');
            if (completedTasksTab.style.display !== 'none') {
                const completedTasks = allTasks.filter(task => 
                    task.subtasks.length > 0 && task.subtasks.every(st => st.status === 'completed')
                );
                displayFilteredTasks(document.getElementById('completedTasksList'), completedTasks, 'completed');
            }
        }

        // Approval Requests Functions
        async function loadApprovalRequests() {
            loadTransferRequests();
            const container = document.getElementById('approvalRequestsList');
            
            if (pendingRequests.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="check-circle-2"></i></div>
                        <h3>No Pending Requests</h3>
                        <p>All member requests have been processed</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = pendingRequests.map(request => `
                <div class="request-card" id="request-${request.id}">
                    <div class="request-header">
                        <div class="request-info">
                            <div class="request-name">${escapeHtml(request.name)}</div>
                            <div class="request-email">${escapeHtml(request.email)}</div>
                            <div class="request-meta">
                                Requested to join on ${request.date_joined ? new Date(request.date_joined).toLocaleDateString() : 'Unknown Date'}
                            </div>
                        </div>
                        <div class="request-actions">
                            <button class="btn btn-success btn-sm" onclick="approveMember('${request.id}')">
                                Approve
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="rejectMember('${request.id}')">
                                Reject
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function approveMember(userId) {
            try {
                const response = await fetch(`${API_BASE}/auth/approve-member/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        userId: userId,
                        teamCode: currentUser.team_code,
                        approvedBy: currentUser.id
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Member approved successfully!', 'success');
                    
                    // Remove from pending requests immediately
                    const requestIndex = pendingRequests.findIndex(req => req.id === userId);
                    if (requestIndex > -1) {
                        pendingRequests.splice(requestIndex, 1);
                    }
                    
                    // Update UI immediately
                    document.getElementById(`request-${userId}`)?.remove();
                    updatePendingRequestsBadge();
                    
                    // Reload team members to show the newly approved member
                    await loadAllTeamMembers();
                    updateDashboardStats();
                    
                    // If no more requests, show empty state
                    if (pendingRequests.length === 0) {
                        document.getElementById('approvalRequestsList').innerHTML = `
                            <div class="empty-state">
                                <div class="icon"><i data-lucide="check-circle-2"></i></div>
                                <h3>No Pending Requests</h3>
                                <p>All member requests have been processed</p>
                            </div>
                        `;
                        return;
                    }
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error approving member:', error);
                showMessage('Failed to approve member', 'error');
            }
        }

        async function rejectMember(userId) {
            try {
                const response = await fetch(`${API_BASE}/auth/reject-member/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        userId: userId,
                        teamCode: currentUser.team_code,
                        rejectedBy: currentUser.id
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Member request rejected', 'success');
                    
                    // Remove from pending requests immediately
                    const requestIndex = pendingRequests.findIndex(req => req.id === userId);
                    if (requestIndex > -1) {
                        pendingRequests.splice(requestIndex, 1);
                    }
                    
                    // Update UI immediately
                    document.getElementById(`request-${userId}`)?.remove();
                    updatePendingRequestsBadge();
                    
                    // Add to rejected members and update rejected tab
                    rejectedMembers.unshift(result.user);
                    updateRejectedMembersDisplay();
                    
                    // If no more requests, show empty state
                    if (pendingRequests.length === 0) {
                        document.getElementById('approvalRequestsList').innerHTML = `
                            <div class="empty-state">
                                <div class="icon"><i data-lucide="check-circle-2"></i></div>
                                <h3>No Pending Requests</h3>
                                <p>All member requests have been processed</p>
                            </div>
                        `;
                        return;
                    }
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error rejecting member:', error);
                showMessage('Failed to reject member', 'error');
            }
        }

        function updateRejectedMembersDisplay() {
            const container = document.getElementById('rejectedMembersList');
            
            if (rejectedMembers.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="check-circle-2"></i></div>
                        <h3>No Rejected Members</h3>
                        <p>No member requests have been rejected yet</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = rejectedMembers.map(member => `
                <div class="member-card" id="rejected-member-${member.id}">
                    <div class="member-avatar">
                        ${escapeHtml(member.name).charAt(0).toUpperCase()}
                    </div>
                    <div class="member-name">${escapeHtml(member.name)}</div>
                    <div class="member-email">${escapeHtml(member.email)}</div>
                    <div class="status-badge status-rejected">REJECTED</div>
                    <div class="request-meta" style="margin: 10px 0; color: #888;">
                        Rejected on ${member.rejected_at ? new Date(member.rejected_at).toLocaleDateString() : 'Recently'}
                    </div>
                    <div class="member-actions">
                        <button class="btn btn-info btn-sm" onclick="approveRejectedMember('${member.id}')">
                            Approve Again
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="deleteRejectedMember('${member.id}')">
                            Delete
                        </button>
                    </div>
                </div>
            `).join('');
        }

        async function approveRejectedMember(userId) {
            try {
                const response = await fetch(`${API_BASE}/auth/approve-rejected-member/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        userId: userId,
                        teamCode: currentUser.team_code,
                        approvedBy: currentUser.id
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Member approved successfully!', 'success');
                    
                    // Remove from rejected members immediately
                    const rejectedIndex = rejectedMembers.findIndex(member => member.id === userId);
                    if (rejectedIndex > -1) {
                        rejectedMembers.splice(rejectedIndex, 1);
                    }
                    
                    // Update UI immediately
                    document.getElementById(`rejected-member-${userId}`)?.remove();
                    
                    // Reload team members to show the newly approved member
                    await loadAllTeamMembers();
                    updateDashboardStats();
                    
                    // Update rejected members display
                    updateRejectedMembersDisplay();
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error approving rejected member:', error);
                showMessage('Failed to approve member', 'error');
            }
        }

        async function deleteRejectedMember(userId) {
            if (!confirm('Are you sure you want to permanently delete this rejected member record?')) {
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/auth/delete-rejected-member/${userId}/`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' }
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Rejected member record deleted permanently', 'success');
                    
                    // Remove from rejected members immediately
                    const rejectedIndex = rejectedMembers.findIndex(member => member.id === userId);
                    if (rejectedIndex > -1) {
                        rejectedMembers.splice(rejectedIndex, 1);
                    }
                    
                    // Update UI immediately
                    document.getElementById(`rejected-member-${userId}`)?.remove();
                    
                    // Update rejected members display
                    updateRejectedMembersDisplay();
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error deleting rejected member:', error);
                showMessage('Failed to delete rejected member', 'error');
            }
        }

        // Task Management Functions
        async function loadAllTasksForManagement() {
            try {
                const response = await fetch(`${API_BASE}/tasks/team/${currentUser.team_code}/`);
                if (response.ok) {
                    let data = await response.json();
                    allTasks = data.results || data;
                    applyTaskSort(); // Sort and display
                } else {
                    console.error('Failed to load tasks for management');
                    displayTasksForManagement([]);
                }
            } catch (error) {
                console.error('Error loading tasks for management:', error);
                showMessage('Failed to load tasks', 'error');
                displayTasksForManagement([]);
            }
        }

        function displayTasksForManagement(tasks) {
            const container = document.getElementById('allTasksManagement');
            
            if (tasks.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="inbox"></i></div>
                        <h3>No Tasks Created</h3>
                        <p>Create your first task to get started</p>
                        <button class="btn btn-primary" onclick="showCreateTaskModal()">
                            Create First Task
                        </button>
                    </div>
                `;
                return;
            }

            container.innerHTML = tasks.map(task => `
                <div class="task-card" onclick="showTaskDetail('${task.id}')" style="cursor: pointer;">
                    <div class="task-header">
                        <div>
                            <div class="task-title">${escapeHtml(task.title)}</div>
                            <div class="task-description">${escapeHtml(task.description || 'No description')}</div>
                        </div>
                        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 5px;">
                            <span class="priority-badge priority-${task.priority || 'medium'}">${escapeHtml(task.priority || 'medium')}</span>
                            <span class="status-badge ${getTaskStatusClass(task)}">${getTaskStatusText(task)}</span>
                        </div>
                    </div>
                    
                    <div class="progress-section">
                        <div class="progress-info">
                            <span>Progress</span>
                            <span>${calculateProgress(task)}%</span>
                        </div>
                        <div class="progress-bar">
                            <div class="progress" style="width: ${calculateProgress(task)}%"></div>
                        </div>
                    </div>

                    <div class="task-meta">
                        <div>
                            <span style="color: #666; font-size: 0.9rem;">
                                ${task.subtasks.length} subtasks • Created by ${escapeHtml(task.created_by_name)}
                            </span>
                        </div>
                        <div class="task-actions">
                            <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); editTask('${task.id}')">
                                Edit
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); deleteTask('${task.id}')">
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Edit Task Functionality
        function renderEditSubtask(subtask) {
                    const historicalAssignee = subtask.assigned_to && !teamMembers.some(member => member.id === subtask.assigned_to);
                    const deadlineDate = WizDeskAPI.toLocalInput(subtask.deadline);
                    return `
                    <div class="edit-subtask-item" data-subtask-id="${subtask.id}">
                        <input type="text" class="edit-subtask-input" aria-label="Subtask title" value="${escapeAttr(subtask.title)}" placeholder="Subtask title" required>
                        <textarea class="edit-subtask-desc" aria-label="Subtask description" placeholder="Subtask description">${escapeHtml(subtask.description || '')}</textarea>
                        <input type="datetime-local" class="edit-subtask-deadline" aria-label="Subtask deadline" value="${deadlineDate}" title="Due Date (Optional)">
                        <select class="form-select edit-subtask-priority" aria-label="Subtask priority">
                            <option value="low" ${subtask.priority === 'low' ? 'selected' : ''}>Low</option>
                            <option value="medium" ${subtask.priority === 'medium' || !subtask.priority ? 'selected' : ''}>Medium</option>
                            <option value="high" ${subtask.priority === 'high' ? 'selected' : ''}>High</option>
                        </select>
                        <select class="form-select assignee-select" aria-label="Assignee">
                            <option value="">Not assigned</option>
                            ${historicalAssignee ? `<option value="${escapeAttr(subtask.assigned_to)}" selected>${escapeHtml(subtask.assigned_to_name || 'Former member')} (historical assignment)</option>` : ''}
                            ${teamMembers.filter(m => m.role.toUpperCase() !== 'LEADER').map(member => 
                                `<option value="${member.id}" ${subtask.assigned_to === member.id ? 'selected' : ''}>
                                    ${escapeHtml(member.name)} - ${escapeHtml(member.email)}
                                </option>`
                            ).join('')}
                        </select>
                        <button type="button" class="remove-subtask" onclick="removeEditSubtask(this)">Remove</button>
                    </div>
                `
        }

        function addEditSubtask() {
            const container = document.getElementById('editSubtasksContainer');
            container.insertAdjacentHTML('beforeend', renderEditSubtask({
                id: `new-${crypto.randomUUID()}`, title: '', description: '', priority: 'medium', assigned_to: null
            }));
            container.lastElementChild.querySelector('input').focus();
        }

        async function editTask(taskId) {
            try {
                const response = await fetch(`${API_BASE}/tasks/${taskId}/`);
                if (!response.ok) {
                    throw new Error('Failed to fetch task');
                }
                const task = await response.json();
                
                editingTaskSnapshot = task;
                // Populate edit form
                document.getElementById('editTaskId').value = task.id;
                document.getElementById('editTaskTitle').value = task.title;
                document.getElementById('editTaskDescription').value = task.description || '';
                document.getElementById('editTaskPriority').value = task.priority || 'medium';
                
                // Populate subtasks for editing
                const subtasksContainer = document.getElementById('editSubtasksContainer');
                subtasksContainer.innerHTML = task.subtasks.map(renderEditSubtask).join('');
                
                showModal('editTaskModal');
            } catch (error) {
                console.error('Error loading task for editing:', error);
                showMessage('Failed to load task details', 'error');
            }
        }

        async function updateTask() {
            const taskId = document.getElementById('editTaskId').value;
            const title = document.getElementById('editTaskTitle').value;
            const description = document.getElementById('editTaskDescription').value;
            const priority = document.getElementById('editTaskPriority').value;
            
            // Collect subtask updates
            const subtaskItems = document.querySelectorAll('#editSubtasksContainer .edit-subtask-item');
            const subtaskUpdates = Array.from(subtaskItems).map(item => {
                const subtaskId = item.getAttribute('data-subtask-id');
                const title = item.querySelector('.edit-subtask-input').value;
                const description = item.querySelector('.edit-subtask-desc').value;
                const deadline = item.querySelector('.edit-subtask-deadline').value;
                const subtaskPriority = item.querySelector('.edit-subtask-priority').value;
                const assignedTo = item.querySelector('.assignee-select').value;
                const original = editingTaskSnapshot.subtasks.find(child => child.id === subtaskId);
                
                return {
                    ...(subtaskId && !subtaskId.startsWith('new-') ? {id: subtaskId} : {}),
                    title,
                    description,
                    deadline: WizDeskAPI.toUTC(deadline),
                    priority: subtaskPriority,
                    ...(!original || original.assigned_to !== (assignedTo || null) ? {assigned_to: assignedTo || null} : {})
                };
            });

            try {
                // Update main task
                const taskResponse = await fetch(`${API_BASE}/tasks/${taskId}/`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title,
                        description,
                        priority,
                        subtasks: subtaskUpdates,
                        deleted_subtask_ids: editingTaskSnapshot.subtasks.map(s => s.id).filter(id => !subtaskUpdates.some(s => s.id === id)),
                        expected_updated_at: editingTaskSnapshot.updated_at
                    })
                });

                if (!taskResponse.ok) {
                    const error = await taskResponse.json();
                    throw new Error(error.error || 'Failed to update task');
                }

                showMessage('Task updated successfully!', 'success');
                closeModal('editTaskModal');
                // Update tasks immediately
                const savedTask = (await taskResponse.json()).task;
                allTasks = allTasks.map(task => task.id === taskId ? savedTask : task);
                if (!allTasks.some(task => task.id === taskId)) allTasks.push(savedTask);
                updateTaskDisplays();
            } catch (error) {
                console.error('Error updating task:', error);
                showMessage(error.message || 'Failed to update task', 'error');
            }
        }

        function removeEditSubtask(button) {
            button.parentElement.remove();
        }

        // Task Search and Filtering
        function handleTaskSearch(query) {
            const searchTerm = query.toLowerCase();
            const taskCards = document.querySelectorAll('.task-list .task-card');
            
            taskCards.forEach(card => {
                const title = card.querySelector('.task-title').textContent.toLowerCase();
                const desc = card.querySelector('.task-description').textContent.toLowerCase();
                
                if (title.includes(searchTerm) || desc.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }

        function applyTaskSort(criterion) {
            const currentSort = criterion || document.getElementById('taskSortSelect').value;
            let sortedTasks = [...allTasks];
            
            switch(currentSort) {
                case 'newest':
                    sortedTasks.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                    break;
                case 'oldest':
                    sortedTasks.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                    break;
                case 'subtasks':
                    sortedTasks.sort((a, b) => (b.subtasks ? b.subtasks.length : 0) - (a.subtasks ? a.subtasks.length : 0));
                    break;
                case 'progress':
                    sortedTasks.sort((a, b) => calculateProgress(b) - calculateProgress(a));
                    break;
            }
            
            displayTasksForManagement(sortedTasks);
        }

        // Countdown Timer Logic
        function getCountdown(deadline) {
            if (!deadline) return null;
            const now = new Date();
            const target = new Date(deadline);
            const diff = target - now;
            
            if (diff <= 0) return "Overdue";
            
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            
            if (hours >= 24) return null; // Only show countdown for < 24h

            return `<span style="color: var(--color-danger, #f04438); font-weight: 600;">${hours}h ${minutes}m remaining</span>`;
        }

        async function loadTasksByStatus(status) {
            try {
                const response = await fetch(`${API_BASE}/tasks/team/${currentUser.team_code}/status/${status}/`);
                if (response.ok) {
                    let data = await response.json();
                    const tasks = data.results || data;
                    
                    if (status === 'active') {
                        displayActiveTasks(tasks);
                    } else if (status === 'completed') {
                        displayCompletedTasks(tasks);
                    }
                } else {
                    console.error('Failed to load tasks by status');
                    if (status === 'active') {
                        displayActiveTasks([]);
                    } else if (status === 'completed') {
                        displayCompletedTasks([]);
                    }
                }
            } catch (error) {
                console.error('Error loading tasks by status:', error);
                showMessage('Failed to load tasks', 'error');
                if (status === 'active') {
                    displayActiveTasks([]);
                } else if (status === 'completed') {
                    displayCompletedTasks([]);
                }
            }
        }

        function displayActiveTasks(tasks) {
            const container = document.getElementById('activeTasksList');
            const activeTasks = tasks.filter(task => 
                task.subtasks.some(subtask => subtask.status !== 'completed')
            );
            
            displayFilteredTasks(container, activeTasks, 'active');
        }

        function displayCompletedTasks(tasks) {
            const container = document.getElementById('completedTasksList');
            const completedTasks = tasks.filter(task => 
                task.subtasks.length > 0 && task.subtasks.every(st => st.status === 'completed')
            );
            
            displayFilteredTasks(container, completedTasks, 'completed');
        }

        function displayFilteredTasks(container, tasks, type) {
            if (tasks.length === 0) {
                const icon = type === 'active' ? 'edit' : 'check-circle-2';
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="${icon}"></i></div>
                        <h3>No ${type} Tasks</h3>
                        <p>${type === 'active' ? 'All tasks are completed!' : 'Complete some tasks to see them here.'}</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = tasks.map(task => {
                const isCompleted = task.subtasks.length > 0 && task.subtasks.every(st => st.status === 'completed');
                const statusText = isCompleted ? 'Completed' : 'In Progress';
                const statusClass = isCompleted ? 'status-completed' : 'status-in-progress';

                return `
                    <div class="task-card" onclick="showTaskDetail('${task.id}')" style="cursor: pointer;">
                        <div class="task-header">
                            <div>
                                <div class="task-title">${escapeHtml(task.title)}</div>
                                <div class="task-description">${escapeHtml(task.description || 'No description')}</div>
                            </div>
                            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 5px;">
                                <span class="priority-badge priority-${task.priority || 'medium'}">${escapeHtml(task.priority || 'medium')}</span>
                                <span class="status-badge ${statusClass}">${statusText}</span>
                            </div>
                        </div>
                        
                        <div class="progress-section">
                            <div class="progress-info">
                                <span>Progress</span>
                                <span>${calculateProgress(task)}%</span>
                            </div>
                            <div class="progress-bar">
                                <div class="progress" style="width: ${calculateProgress(task)}%"></div>
                            </div>
                        </div>

                        <div class="task-meta">
                            <div>
                                <span style="color: #666; font-size: 0.9rem;">
                                    ${task.subtasks.length} subtasks • Created by ${escapeHtml(task.created_by_name)}
                                </span>
                            </div>
                            <div class="task-actions">
                                <button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); editTask('${task.id}')">
                                    Edit
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Helper functions for task status
        function getTaskStatusClass(task) {
            const isCompleted = task.subtasks.length > 0 && task.subtasks.every(st => st.status === 'completed');
            const hasAssigned = task.subtasks.some(st => st.status === 'assigned' || st.status === 'taken');
            
            if (isCompleted) return 'status-completed';
            if (hasAssigned) return 'status-in-progress';
            return 'status-available';
        }

        function getTaskStatusText(task) {
            const isCompleted = task.subtasks.length > 0 && task.subtasks.every(st => st.status === 'completed');
            const hasAssigned = task.subtasks.some(st => st.status === 'assigned' || st.status === 'taken');
            
            if (isCompleted) return 'Completed';
            if (hasAssigned) return 'In Progress';
            return 'Available';
        }

        // Member Management Functions
        async function loadAllTeamMembers() {
            try {
                const response = await fetch(`${API_BASE}/auth/team/${currentUser.team_code}/all-members/`);
                if (response.ok) {
                    const members = await response.json();
                    teamMembers = members;
                    displayAllTeamMembers(members);
                } else {
                    console.error('Failed to load team members');
                    teamMembers = [];
                    displayAllTeamMembers([]);
                }
            } catch (error) {
                console.error('Error loading team members:', error);
                showMessage('Failed to load team members', 'error');
                teamMembers = [];
                displayAllTeamMembers([]);
            }
        }

        function displayAllTeamMembers(members) {
            const container = document.getElementById('membersList');
            
            if (members.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="users"></i></div>
                        <h3>No Team Members</h3>
                        <p>Team members will appear here when they join</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = members.map(member => `
                <div class="member-card">
                    <div class="member-avatar">
                        ${escapeHtml(member.name).charAt(0).toUpperCase()}
                    </div>
                    <div class="member-name">${escapeHtml(member.name)}</div>
                    <div class="member-email">${escapeHtml(member.email)}</div>
                    <div class="member-role ${member.role}">${escapeHtml(member.role.toUpperCase())}</div>
                    <div class="member-stats">
                        <div class="stat">
                            <div class="stat-value">${member.assigned_tasks || 0}</div>
                            <div class="stat-label">Tasks</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">${member.completed_tasks || 0}</div>
                            <div class="stat-label">Completed</div>
                        </div>
                    </div>
                    ${(member.role === 'member' || member.role === 'MEMBER') ? `
                        <div class="member-actions">
                            <button class="btn btn-sm btn-danger" data-member-id="${escapeAttr(member.id)}" data-member-name="${escapeAttr(member.name)}" onclick="deleteMemberFromEl(this)">
                                Remove
                            </button>
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }

        async function deleteMember(memberId, memberName) {
            if (!confirm(`Are you sure you want to remove ${memberName} from the team?`)) {
                return;
            }
            try {
                const response = await fetch(`${API_BASE}/auth/team/${currentUser.team_code}/member/${memberId}/`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ leaderId: currentUser.id })
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Member removed successfully!', 'success');
                    loadAllTeamMembers(); // Refresh members list
                    updateDashboardStats();
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                console.error('Error deleting member:', error);
                showMessage('Failed to remove member', 'error');
            }
        }

        // Secure wrapper: user-controlled name travels via data-*
        // attributes (HTML-escaped at render), never interpolated
        // into an inline JS string.
        function deleteMemberFromEl(el) {
            deleteMember(el.dataset.memberId, el.dataset.memberName);
        }

        // Task Creation Functions - UPDATED with subtask description and member search
        function showCreateTaskModal() {
            // Reset form
            document.getElementById('createTaskForm').reset();
            
            // Reset assignment section
            selectedMembers = [];
            updateSelectedMembersList();
            document.getElementById('assignmentToggle').classList.remove('active');
            document.getElementById('assignmentSection').style.display = 'none';
            
            // Reset subtasks to one empty field
            document.getElementById('subtasksContainer').innerHTML = `
                <div class="subtask-item">
                    <input type="text" class="subtask-input" placeholder="Subtask title (e.g., Design homepage)" required>
                    <textarea class="subtask-desc" placeholder="Subtask description (Optional)"></textarea>
                    <div class="subtask-field">
                        <label class="subtask-field-label">Deadline</label>
                        <input type="datetime-local" class="subtask-deadline" title="Due Date (Optional)">
                    </div>
                    <div class="subtask-field">
                        <label class="subtask-field-label">Priority</label>
                        <select class="form-select subtask-priority">
                            <option value="low">Low</option>
                            <option value="medium" selected>Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                    <div class="subtask-field assignee-field" style="display: none;">
                        <label class="subtask-field-label">Assign To</label>
                        <select class="form-select assignee-select" aria-label="Assignee">
                            <option value="">Select member...</option>
                        </select>
                    </div>
                    <button type="button" class="remove-subtask" onclick="removeSubtask(this)">Remove</button>
                </div>`;
            
            // Populate members checklist
            const checklist = document.getElementById('membersChecklist');
            checklist.innerHTML = teamMembers.filter(m => m.role.toUpperCase() !== 'LEADER').map(member => `
                <div class="member-item-row">
                    <input type="checkbox" id="member-${member.id}" value="${member.id}" class="member-checkbox" onchange="toggleMemberSelection('${member.id}', this.checked)">
                    <label for="member-${member.id}" style="flex: 1; cursor: pointer;">
                        <div style="font-weight: 500;">${escapeHtml(member.name)}</div>
                        <div style="font-size: 0.9rem; color: var(--text-secondary);">${escapeHtml(member.email)}</div>
                    </label>
                </div>
            `).join('');
            
            showModal('createTaskModal');
        }

        function toggleAssignment() {
            const toggle = document.getElementById('assignmentToggle');
            const section = document.getElementById('assignmentSection');
            const isActive = toggle.classList.toggle('active');
            
            section.style.display = isActive ? 'block' : 'none';
            
            // Show/hide assignee dropdowns and labels in subtasks
            const assigneeFields = document.querySelectorAll('.assignee-field');
            assigneeFields.forEach(field => {
                field.style.display = isActive ? 'block' : 'none';
            });
            
            if (isActive) {
                // Populate assignee dropdowns with selected members only
                updateAssigneeDropdowns();
            }
        }

        function filterMembers() {
            const searchTerm = document.getElementById('memberSearch').value.toLowerCase();
            const checkboxes = document.querySelectorAll('.member-checkbox');
            
            checkboxes.forEach(checkbox => {
                const memberId = checkbox.value;
                const member = teamMembers.find(m => m.id == memberId);
                const memberItem = checkbox.closest('div');
                
                if (member && (
                    member.name.toLowerCase().includes(searchTerm) || 
                    member.email.toLowerCase().includes(searchTerm)
                )) {
                    memberItem.style.display = 'flex';
                } else {
                    memberItem.style.display = 'none';
                }
            });
        }

        function toggleMemberSelection(memberId, isSelected) {
            const member = teamMembers.find(m => m.id == memberId);
            
            if (isSelected) {
                if (!selectedMembers.some(m => m.id == memberId)) {
                    selectedMembers.push(member);
                }
            } else {
                selectedMembers = selectedMembers.filter(m => m.id != memberId);
            }
            
            updateSelectedMembersList();
            updateAssigneeDropdowns();
        }

        function updateSelectedMembersList() {
            const container = document.getElementById('selectedMembersList');
            
            if (selectedMembers.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 20px;">No members selected</div>';
                return;
            }
            
            container.innerHTML = selectedMembers.map(member => `
                <div class="selected-member-item">
                    <div>
                        <div style="font-weight: 500; color: var(--text-primary);">${escapeHtml(member.name)}</div>
                        <div style="font-size: 0.9rem; color: var(--text-secondary);">${escapeHtml(member.email)}</div>
                    </div>
                    <button type="button" class="remove-member-btn" onclick="removeSelectedMember('${member.id}')">Remove</button>
                </div>
            `).join('');
        }

        function removeSelectedMember(memberId) {
            selectedMembers = selectedMembers.filter(m => m.id != memberId);
            
            // Uncheck the checkbox
            const checkbox = document.getElementById(`member-${memberId}`);
            if (checkbox) {
                checkbox.checked = false;
            }
            
            updateSelectedMembersList();
            updateAssigneeDropdowns();
        }

        function updateAssigneeDropdowns() {
            const assignSelects = document.querySelectorAll('.assignee-select');
            
            assignSelects.forEach(select => {
                select.innerHTML = '<option value="">Select member...</option>' +
                    selectedMembers.map(member => 
                        `<option value="${member.id}">${escapeHtml(member.name)} - ${escapeHtml(member.email)}</option>`
                    ).join('');
            });
        }

        function addSubtaskField() {
            const container = document.getElementById('subtasksContainer');
            const subtaskDiv = document.createElement('div');
            subtaskDiv.className = 'subtask-item';
            
            const isAssignmentActive = document.getElementById('assignmentToggle').classList.contains('active');
            
            subtaskDiv.innerHTML = `
                <input type="text" class="subtask-input" placeholder="Subtask title" required>
                <textarea class="subtask-desc" placeholder="Subtask description (Optional)"></textarea>
                <div class="subtask-field">
                    <label class="subtask-field-label">Deadline</label>
                    <input type="datetime-local" class="subtask-deadline" title="Due Date (Optional)">
                </div>
                <div class="subtask-field">
                    <label class="subtask-field-label">Priority</label>
                    <select class="form-select subtask-priority">
                        <option value="low">Low</option>
                        <option value="medium" selected>Medium</option>
                        <option value="high">High</option>
                    </select>
                </div>
                <div class="subtask-field assignee-field" style="display: ${isAssignmentActive ? 'block' : 'none'};">
                    <label class="subtask-field-label">Assign To</label>
                    <select class="form-select assignee-select" aria-label="Assignee">
                        <option value="">Select member...</option>
                        ${selectedMembers.map(member => 
                            `<option value="${member.id}">${escapeHtml(member.name)} - ${escapeHtml(member.email)}</option>`
                        ).join('')}
                    </select>
                </div>
                <button type="button" class="remove-subtask" onclick="removeSubtask(this)">Remove</button>
            `;
            container.appendChild(subtaskDiv);
        }

        function removeSubtask(button) {
            if (document.querySelectorAll('.subtask-item').length > 1) {
                button.parentElement.remove();
            } else {
                showMessage('At least one subtask is required', 'error');
            }
        }

        // Form submission
        document.getElementById('createTaskForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            await createTask();
        });

        async function createTask() {
            const title = document.getElementById('taskTitle').value;
            const description = document.getElementById('taskDescription').value;
            const priority = document.getElementById('taskPriority').value;
            const assignSpecific = document.getElementById('assignmentToggle').classList.contains('active');
            
            // Collect subtasks - UPDATED to include description and priority
            const subtaskItems = document.querySelectorAll('.subtask-item');
            const subtasks = Array.from(subtaskItems).map(item => {
                const title = item.querySelector('.subtask-input').value;
                const description = item.querySelector('.subtask-desc').value;
                const deadline = item.querySelector('.subtask-deadline').value;
                const subtaskPriority = item.querySelector('.subtask-priority').value;
                const assigneeSelect = item.querySelector('.assignee-select');
                const assignedTo = assignSpecific && assigneeSelect ? assigneeSelect.value : null;
                
                return {
                    title: title,
                    description: description,
                    deadline: WizDeskAPI.toUTC(deadline),
                    priority: subtaskPriority,
                    assigned_to: assignedTo || null
                };
            });

            if (subtasks.length === 0) {
                showMessage('Please add at least one subtask', 'error');
                return;
            }

            const taskData = {
                title,
                description,
                priority,
                teamCode: currentUser.team_code,
                createdBy: currentUser.id,
                subtasks,
                assignSpecific
            };

            try {
                const response = await fetch(`${API_BASE}/tasks/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(taskData)
                });

                const result = await response.json();

                if (response.ok) {
                    showMessage('Task created successfully!');
                    closeModal('createTaskModal');
                    document.getElementById('createTaskForm').reset();
                    // Reset to one subtask
                    document.getElementById('subtasksContainer').innerHTML = `
                        <div class="subtask-item">
                            <input type="text" class="subtask-input" placeholder="Subtask title" required>
                            <textarea class="subtask-desc" placeholder="Subtask description (Optional)"></textarea>
                            <div class="subtask-field">
                                <label class="subtask-field-label">Deadline</label>
                                <input type="datetime-local" class="subtask-deadline" title="Due Date (Optional)">
                            </div>
                            <div class="subtask-field">
                                <label class="subtask-field-label">Priority</label>
                                <select class="form-select subtask-priority">
                                    <option value="low">Low</option>
                                    <option value="medium" selected>Medium</option>
                                    <option value="high">High</option>
                                </select>
                            </div>
                            <div class="subtask-field assignee-field" style="display: none;">
                                <label class="subtask-field-label">Assign To</label>
                                <select class="form-select assignee-select" aria-label="Assignee">
                                    <option value="">Select member...</option>
                                </select>
                            </div>
                            <button type="button" class="remove-subtask" onclick="removeSubtask(this)">Remove</button>
                        </div>
                    `;
                    // Reset assignment toggle
                    document.getElementById('assignmentToggle').classList.remove('active');
                    document.getElementById('assignmentSection').style.display = 'none';
                    // Reset selected members
                    selectedMembers = [];
                    updateSelectedMembersList();
                    
                    // Reload tasks to get the new task with its ID
                    await loadTasks();
                    // Update all displays
                    updateTaskDisplays();
                } else {
                    showMessage(result.error, 'error');
                }
            } catch (error) {
                showMessage('Failed to create task', 'error');
            }
        }

        // NEW FEATURES: Task Detail View
        async function showTaskDetail(taskId) {
            try {
                const response = await fetch(`${API_BASE}/tasks/${taskId}/`);
                if (!response.ok) {
                    throw new Error('Failed to fetch task details');
                }
                const task = await response.json();
                
                // Populate task details
                document.getElementById('detailTaskTitle').textContent = task.title;
                document.getElementById('detailTaskDescription').textContent = task.description || 'No description provided';
                
                // Set status badge
                const statusBadge = document.getElementById('detailTaskStatus');
                statusBadge.textContent = getTaskStatusText(task);
                statusBadge.className = `status-badge ${getTaskStatusClass(task)}`;
                
                // Set metadata
                document.getElementById('detailCreatedBy').textContent = task.created_by_name || 'Unknown';
                document.getElementById('detailCreatedAt').textContent = new Date(task.created_at).toLocaleDateString();
                
                // Calculate completion date (last subtask completion)
                const completedSubtasks = task.subtasks.filter(st => st.status === 'completed');
                let completedDate = null;
                if (completedSubtasks.length > 0) {
                    // Find the latest completion date
                    completedDate = new Date(Math.max(...completedSubtasks.map(st => new Date(st.completed_at || st.updated_at))));
                    document.getElementById('detailCompletedAt').textContent = completedDate.toLocaleDateString();
                } else {
                    document.getElementById('detailCompletedAt').textContent = 'Not completed';
                }
                
                // Set progress
                const progress = calculateProgress(task);
                document.getElementById('detailProgress').textContent = `${progress}%`;
                
                // Populate subtasks
                const subtasksContainer = document.getElementById('detailSubtasksList');
                subtasksContainer.innerHTML = task.subtasks.map(subtask => {
                    const assignee = teamMembers.find(m => m.id === subtask.assigned_to);
                    const assigneeName = assignee ? assignee.name : 'Not assigned';
                    const completedDate = subtask.status === 'completed' && subtask.completed_at 
                        ? new Date(subtask.completed_at).toLocaleDateString() 
                        : 'Not completed';
                    const deadline = subtask.deadline 
                        ? new Date(subtask.deadline).toLocaleString() 
                        : 'No deadline';
                    
                    const countdown = getCountdown(subtask.deadline);
                    return `
                        <div class="detail-subtask-item">
                            <div class="detail-subtask-info">
                                <div class="detail-subtask-title">${escapeHtml(subtask.title)} ${countdown ? `(${countdown})` : ''}</div>
                                <div class="detail-subtask-description" style="color: #666; margin-bottom: 5px;">${escapeHtml(subtask.description || 'No description')}</div>
                                <div class="detail-subtask-assignee">
                                    <strong>Due Date:</strong> ${deadline} | 
                                    <strong>Assigned to:</strong> ${escapeHtml(assigneeName)} | 
                                    <strong>Status:</strong> ${subtask.status} | 
                                    <strong>Completed:</strong> ${completedDate}
                                </div>
                            </div>
                            <span class="detail-subtask-status ${getSubtaskStatusClass(subtask)}">${subtask.status}</span>
                        </div>
                    `;
                }).join('');
                
                // Set up edit button
                document.getElementById('detailEditBtn').onclick = function() {
                    closeModal('taskDetailModal');
                    editTask(taskId);
                };
                
                showModal('taskDetailModal');
            } catch (error) {
                console.error('Error loading task details:', error);
                showMessage('Failed to load task details', 'error');
            }
        }

        function getSubtaskStatusClass(subtask) {
            switch(subtask.status) {
                case 'completed': return 'status-completed';
                case 'in-progress': return 'status-in-progress';
                case 'assigned': return 'status-assigned';
                case 'available': return 'status-available';
                default: return 'status-pending';
            }
        }

        // NEW PERFORMANCE TAB FUNCTIONS
        async function loadPerformanceData(isSilent = false) {
            try {
                if (!isSilent) {
                    // Only display loading messages for initial/manual load
                    document.getElementById('topPerformersGrid').innerHTML = '<p style="text-align: center; padding: 20px;">Loading top performers...</p>';
                    document.getElementById('membersPerformanceTable').innerHTML = '<p style="text-align: center; padding: 20px;">Loading performance data...</p>';
                }

                // Load performance data from API
                const response = await fetch(`${API_BASE}/performance/team/${currentUser.team_code}/`);
                if (response.ok) {
                    const data = await response.json();
                    memberPerformanceData = (data && Array.isArray(data.memberStats)) ? data.memberStats : [];
                    displayPerformanceData();
                } else {
                    console.error('Failed to load performance data');
                    memberPerformanceData = [];
                    displayPerformanceData();
                }
            } catch (error) {
                console.error('Error loading performance data:', error);
                showMessage('Failed to load performance data', 'error');
                memberPerformanceData = [];
                displayPerformanceData();
            }
        }

        function displayPerformanceData() {
            displayTopPerformers();
            filterPerformanceData();
        }

        function displayTopPerformers() {
            const container = document.getElementById('topPerformersGrid');
            
            if (memberPerformanceData.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="bar-chart-3"></i></div>
                        <h3>No Performance Data</h3>
                        <p>No team members have completed tasks yet</p>
                    </div>
                `;
                return;
            }

            // Sort members by completed tasks (descending) and take top 3
            const topPerformers = [...memberPerformanceData]
                .sort((a, b) => (b.completed_tasks || 0) - (a.completed_tasks || 0))
                .filter(m => (m.completed_tasks || 0) > 0)
                .slice(0, 3);

            if (topPerformers.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="trophy"></i></div>
                        <h3>No Top Performers</h3>
                        <p>No team members have completed tasks yet</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = topPerformers.map((member, index) => {
                const rankClass = index === 0 ? 'gold' : index === 1 ? 'silver' : 'bronze';

                return `
                    <div class="top-performer-card ${rankClass}">
                        <div class="rank-badge ${rankClass}"><i data-lucide="medal"></i></div>
                        <div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 10px; color: var(--text-primary);">
                            ${escapeHtml(member.name)}
                        </div>
                        <div style="color: var(--text-secondary); margin-bottom: 15px; font-size: 0.9rem;">
                            ${escapeHtml(member.email)}
                        </div>
                        <div style="display: flex; justify-content: space-around; margin: 20px 0;">
                            <div style="text-align: center;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--accent-color);">${member.assigned_tasks || 0}</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">Assigned</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: #28a745;">${member.completed_tasks || 0}</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">Completed</div>
                            </div>
                        </div>
                        <button class="view-details-btn" onclick="showMemberPerformanceDetails('${member.id}')">
                            View Details
                        </button>
                    </div>
                `;
            }).join('');
        }

        function renderPerformanceTable(data) {
            if (data.length === 0) {
                return `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="search"></i></div>
                        <h3>No Members Found</h3>
                        <p>No members match your criteria</p>
                    </div>
                `;
            }

            return `
                <table class="performance-table">
                    <thead>
                        <tr>
                            <th>Member</th>
                            <th>Tasks Assigned</th>
                            <th>Tasks Completed</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(member => `
                            <tr>
                                <td>
                                    <div class="member-info">
                                        <div class="member-avatar-small">${escapeHtml(member.name).charAt(0).toUpperCase()}</div>
                                        <div class="member-details">
                                            <div class="member-name" onclick="showMemberPerformanceDetails('${member.id}')" style="cursor: pointer;">
                                                ${escapeHtml(member.name)}
                                            </div>
                                            <div class="member-email">${escapeHtml(member.email)}</div>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <div class="task-stats">
                                        <div class="stat-item">
                                            <div class="stat-value">${member.assigned_tasks || 0}</div>
                                            <div class="stat-label">Total</div>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <div class="task-stats">
                                        <div class="stat-item">
                                            <div class="stat-value">${member.completed_tasks || 0}</div>
                                            <div class="stat-label">Completed</div>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <button class="view-details-btn" onclick="showMemberPerformanceDetails('${member.id}')">
                                        View Details
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        function displayMembersPerformanceTable() {
            filterPerformanceData();
        }

        async function showMemberPerformanceDetails(memberId) {
            try {
                // Find member data
                const member = memberPerformanceData.find(m => m.id === memberId);
                if (!member) {
                    showMessage('Member not found', 'error');
                    return;
                }

                // Load member's completed tasks
                const tasksResponse = await fetch(`${API_BASE}/tasks/user/${memberId}/subtasks/`);
                let completedTasks = [];
                if (tasksResponse.ok) {
                    let data = await tasksResponse.json();
                    const allTasks = data.results || data;
                    completedTasks = allTasks.filter(task => task.progress === 'completed' || task.status === 'completed');
                }

                // Calculate completion rate (backend now provides it, but we can double check)
                const completionRate = member.completion_rate !== undefined 
                    ? member.completion_rate 
                    : (member.assigned_tasks > 0 ? Math.round((member.completed_tasks / member.assigned_tasks) * 100) : 0);

                // Populate modal content
                document.getElementById('memberPerformanceContent').innerHTML = `
                    <div style="margin-bottom: 25px;">
                        <div style="display: flex; flex-direction: column; align-items: center; text-align: center; gap: 15px; margin-bottom: 30px;">
                            <div class="member-avatar" style="width: 80px; height: 80px; font-size: 2rem;">
                                ${escapeHtml(member.name).charAt(0).toUpperCase()}
                            </div>
                            <div>
                                <div style="font-size: 1.8rem; font-weight: 600; color: var(--text-primary);">${escapeHtml(member.name)}</div>
                                <div style="color: var(--text-secondary); font-size: 1.1rem;">${escapeHtml(member.email)}</div>
                            </div>
                        </div>

                        <div class="member-details-grid">
                            <div class="member-detail-card">
                                <div class="member-detail-value">${member.assigned_tasks || 0}</div>
                                <div class="member-detail-label">Total Tasks Assigned</div>
                            </div>
                            <div class="member-detail-card">
                                <div class="member-detail-value">${member.completed_tasks || 0}</div>
                                <div class="member-detail-label">Tasks Completed</div>
                            </div>
                            <div class="member-detail-card">
                                <div class="member-detail-value">${member.active_tasks || 0}</div>
                                <div class="member-detail-label">In Progress</div>
                            </div>
                            <div class="member-detail-card">
                                <div class="member-detail-value">${completionRate}%</div>
                                <div class="member-detail-label">Completion Rate</div>
                            </div>
                        </div>
                    </div>

                    <div>
                        <h3 style="margin-bottom: 15px; color: var(--text-primary);">Completed Tasks</h3>
                        ${completedTasks.length > 0 ? `
                            <div class="completed-tasks-list">
                                ${completedTasks.map(task => `
                                    <div class="completed-task-item">
                                        <div class="completed-task-title">${escapeHtml(task.task_title || 'Task')} - ${escapeHtml(task.title)}</div>
                                        <div class="completed-task-description" style="color: var(--text-secondary); margin: 5px 0;">${escapeHtml(task.description || 'No description')}</div>
                                        <div class="completed-task-meta">
                                            Completed on: ${new Date(task.updated_at).toLocaleDateString()}
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : `
                            <div class="empty-state" style="padding: 30px;">
                                <div class="icon"><i data-lucide="inbox"></i></div>
                                <h3>No Completed Tasks</h3>
                                <p>This member hasn't completed any tasks yet</p>
                            </div>
                        `}
                    </div>
                `;

                showModal('memberPerformanceModal');
            } catch (error) {
                console.error('Error loading member performance details:', error);
                showMessage('Failed to load member details', 'error');
            }
        }

        function filterPerformanceData() {
            const searchTerm = document.getElementById('performanceSearch').value.toLowerCase();
            const activeFilter = document.querySelector('.performance-filters .performance-filter-btn.active').getAttribute('data-filter');
            
            let filteredData = [...memberPerformanceData];
            
            // Apply search filter by name or email
            if (searchTerm) {
                filteredData = filteredData.filter(member => 
                    member.name.toLowerCase().includes(searchTerm) ||
                    member.email.toLowerCase().includes(searchTerm)
                );
            }
            
            // Compute completion rate from completed/assigned counts
            const completionRate = (member) => member.assigned_tasks > 0 ? Math.round((member.completed_tasks / member.assigned_tasks) * 100) : 0;
            
            // Apply performance category filter
            if (activeFilter === 'top') {
                filteredData = filteredData.filter(member => {
                    const rate = member.completion_rate !== undefined ? member.completion_rate : (member.assigned_tasks > 0 ? (member.completed_tasks / member.assigned_tasks) * 100 : 0);
                    return (rate >= 80 || member.completed_tasks > 5) && member.assigned_tasks > 0;
                });
            } else if (activeFilter === 'low') {
                filteredData = filteredData.filter(member => {
                    const rate = member.completion_rate !== undefined ? member.completion_rate : (member.assigned_tasks > 0 ? (member.completed_tasks / member.assigned_tasks) * 100 : 0);
                    return rate < 50 && member.assigned_tasks > 0;
                });
            }
            
            // Update the table display
            const container = document.getElementById('membersPerformanceTable');
            container.innerHTML = renderPerformanceTable(filteredData);
        }
        // ===== TEAM TRANSFER FUNCTIONS =====
        async function loadTransferRequests() {
            try {
                const response = await fetch(`${API_BASE}/auth/transfer/pending/`);
                if (!response.ok) throw new Error('Failed to fetch transfers');
                const data = await response.json();
                
                // Check for new transfer requests
                const hasNew = data.some(t => !lastTransferRequests.find(lt => lt.id === t.id));
                if (!isInitialLoad && hasNew) {
                    const newTransfers = data.filter(t => !lastTransferRequests.find(lt => lt.id === t.id));
                    newTransfers.forEach(t => {
                        const isCurrentLead = t.status === 'PENDING_CURRENT';
                        const title = isCurrentLead ? 'Outgoing Transfer' : 'Incoming Transfer';
                        const msg = isCurrentLead 
                            ? `${escapeHtml(t.member_name)} wants to leave to ${escapeHtml(t.future_team_name)}.`
                            : `${escapeHtml(t.member_name)} wants to join from ${escapeHtml(t.current_team_name)}.`;
                        
                        showToastNotification(title, msg, 'transfer');
                    });
                }
                
                lastTransferRequests = data;
                displayTransferRequests(data);
                updateYellowDots();
            } catch (error) {
                console.error('Error loading transfers:', error);
            }
        }

        function displayTransferRequests(requests) {
            const container = document.getElementById('transferRequestsList');
            if (requests.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="icon"><i data-lucide="arrow-right-left"></i></div>
                        <h3>No Transfer Requests</h3>
                        <p>Team transfer requests requiring your approval will appear here</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = requests.map(req => {
                const isCurrentLead = req.status === 'PENDING_CURRENT';
                const roleText = isCurrentLead ? 'Outgoing Member' : 'Incoming Member';
                const teamText = isCurrentLead ? `to ${escapeHtml(req.future_team_name)}` : `from ${escapeHtml(req.current_team_name)}`;
                
                return `
                    <div class="task-card" id="transfer-request-${req.id}">
                        <div class="task-header">
                            <div>
                                <div class="task-title">${escapeHtml(req.member_name)} (${escapeHtml(req.member_email)})</div>
                                <div class="task-description">${roleText} ${teamText}</div>
                            </div>
                            <span class="status-badge status-assigned">${req.status.replace('_', ' ')}</span>
                        </div>
                        <div class="task-actions" style="margin-top: 15px; display: flex; gap: 10px;">
                            <button class="btn btn-sm btn-primary" onclick="processTransfer('${req.id}', 'approve')">Approve Transfer</button>
                            <button class="btn btn-sm btn-outline" onclick="processTransfer('${req.id}', 'reject')" style="color: #dc3545; border-color: #dc3545;">Reject</button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function processTransfer(requestId, action) {
            showConfirmModal(
                'Confirm Transfer',
                `Are you sure you want to ${action} this transfer request?`,
                async () => {
                    try {
                        const response = await fetch(`${API_BASE}/auth/transfer/${requestId}/process/`, {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${localStorage.getItem('token')}`
                            },
                            body: JSON.stringify({ action: action })
                        });

                        const result = await response.json();

                        if (response.ok) {
                            showMessage(`Transfer ${action}ed successfully!`);
                            loadTransferRequests();
                            loadAllTeamMembers();
                            updateDashboardStats();
                        } else {
                            showMessage(result.error || `Failed to ${action} transfer`, 'error');
                        }
                    } catch (error) {
                        console.error('Error processing transfer:', error);
                        showMessage('An error occurred', 'error');
                    }
                }
            );
        }

        // ===== NOTIFICATION BOX LOGIC =====
        let notifications = [];
        let lastTransferRequests = [];

        function loadNotifications() {
            if (currentUser && currentUser.id) {
                notifications = JSON.parse(localStorage.getItem(`notifs_leader_${currentUser.id}`)) || [];
            }
        }

        function saveNotification(title, message, type) {
            const newNotif = {
                id: Date.now(),
                title,
                message,
                type,
                time: new Date().toISOString(),
                read: false
            };
            notifications.unshift(newNotif);
            if (notifications.length > 20) notifications = notifications.slice(0, 20);
            if (currentUser && currentUser.id) {
                localStorage.setItem(`notifs_leader_${currentUser.id}`, JSON.stringify(notifications));
            }
            updateNotifUI();
            updateYellowDots();
        }

        function updateNotifUI() {
            const list = document.getElementById('notifList');
            const badge = document.getElementById('notifBadge');
            const unreadCount = notifications.filter(n => !n.read).length;

            if (unreadCount > 0) {
                badge.textContent = unreadCount;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }

            if (notifications.length === 0) {
                list.innerHTML = '<div class="notification-empty empty-notifs">No recent notifications</div>';
                return;
            }

            list.innerHTML = notifications.map(n => `
                <div class="notification-item notif-item ${n.read ? '' : 'unread'}" data-nid="${Number(n.id) || 0}" onclick="markAsReadFromEl(this)">
                    <div class="notification-item-icon notif-item-icon">
                        <i data-lucide="${n.type === 'request' ? 'user-check' : n.type === 'transfer' ? 'repeat' : 'bell'}"></i>
                    </div>
                    <div class="notification-item-content notif-item-content">
                        <div class="notification-item-title notif-item-title">${escapeHtml(n.title)}</div>
                        <div class="notification-item-message notif-item-msg">${escapeHtml(n.message)}</div>
                        <div class="notification-item-time notif-item-time">${formatNotifTime(n.time)}</div>
                    </div>
                </div>
            `).join('');
            if (window.WizDeskIcons) window.WizDeskIcons.init();
        }

        function formatNotifTime(isoString) {
            const date = new Date(isoString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            
            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
            return date.toLocaleDateString();
        }

        function toggleNotifDropdown(event) {
            event.stopPropagation();
            const dropdown = document.getElementById('notifDropdown');
            const isOpen = dropdown.getAttribute('aria-hidden') === 'false';
            dropdown.setAttribute('aria-hidden', String(isOpen));
            // clear legacy inline-display state so V2 CSS controls visibility
            dropdown.style.display = '';
        }

        // close dropdown on outside click
        document.addEventListener('click', function(e) {
            const dropdown = document.getElementById('notifDropdown');
            const bell = document.getElementById('notifBell');
            if (dropdown && bell && !dropdown.contains(e.target) && !bell.contains(e.target)) {
                dropdown.setAttribute('aria-hidden', 'true');
            }
        });

        function markAsRead(id) {
            const nid = Number(id);
            const notif = notifications.find(n => Number(n.id) === nid);
            if (notif) {
                notif.read = true;
                if (currentUser && currentUser.id) {
                    localStorage.setItem(`notifs_leader_${currentUser.id}`, JSON.stringify(notifications));
                }
                updateNotifUI();
                updateYellowDots();
            }
        }

        function clearNotifications(event) {
            event.stopPropagation();
            notifications = [];
            if (currentUser && currentUser.id) {
                localStorage.setItem(`notifs_leader_${currentUser.id}`, JSON.stringify(notifications));
            }
            updateNotifUI();
            updateYellowDots();
        }

        function markAsReadFromEl(el) {
            markAsRead(el.dataset.nid);
        }

        function showToastNotification(title, message, type = 'general') {
            saveNotification(title, message, type);
            const container = document.querySelector('.notification-container');
            const toast = document.createElement('div');
            toast.className = 'task-notification';
            const iconName = type === 'request' ? 'user-plus' : type === 'transfer' ? 'arrow-right-left' : type === 'status' ? 'trending-up' : 'bell';
            toast.innerHTML = `
                <div class="notif-icon"><i data-lucide="${iconName}"></i></div>
                <div class="notif-content">
                    <strong class="notif-title">${escapeHtml(title)}</strong>
                    <div class="notif-msg">${escapeHtml(message)}</div>
                </div>
            `;
            if (window.WizDeskIcons) window.WizDeskIcons.init();

            toast.onclick = () => {
                showTab('approval-requests');
                toast.classList.add('closing');
                setTimeout(() => toast.remove(), 500);
            };

            container.appendChild(toast);
            setTimeout(() => {
                toast.classList.add('closing');
                setTimeout(() => toast.remove(), 500);
            }, 5000);
        }

        function updateYellowDots() {
            const approvalDot = document.getElementById('approvalDot');
            const tasksDot = document.getElementById('tasksDot');
            const activeTasksBadge = document.getElementById('activeTasksBadge');
            const completedTasksBadge = document.getElementById('completedTasksBadge');
            const notifBadge = document.getElementById('notifBadge');
            
            const unreadNotifs = notifications.filter(n => !n.read);

            // Bell Badge (Always show total unread)
            if (notifBadge) {
                if (unreadNotifs.length > 0) {
                    notifBadge.textContent = unreadNotifs.length;
                    notifBadge.style.display = 'flex';
                } else {
                    notifBadge.style.display = 'none';
                }
            }

            // Check tab visibility
            const approvalTabVisible = document.getElementById('approval-requests').style.display === 'block';
            const tasksTabVisible = document.getElementById('tasks').style.display === 'block';
            const activeTasksTabVisible = document.getElementById('active-tasks').style.display === 'block';
            const completedTasksTabVisible = document.getElementById('completed-tasks').style.display === 'block';

            // Approval Tab Dot
            if (approvalDot) {
                const hasUnreadRequests = unreadNotifs.some(n => n.type === 'request' || n.type === 'transfer');
                approvalDot.style.display = (!approvalTabVisible && (hasUnreadRequests || pendingRequests.length > 0)) ? 'inline-block' : 'none';
            }

            // Task Management Tab Dot
            if (tasksDot) {
                const hasUnreadStatus = unreadNotifs.some(n => n.type === 'status');
                tasksDot.style.display = (!tasksTabVisible && hasUnreadStatus) ? 'inline-block' : 'none';
            }

            // Active Tasks Dot
            if (activeTasksBadge) {
                activeTasksBadge.style.display = (!activeTasksTabVisible && activeTasksBadge.style.display === 'inline-block') ? 'inline-block' : 'none';
                // Note: activeTasksBadge display is also controlled by checkTaskUpdates, 
                // but we hide it here if tab is visible.
            }

            // Completed Tasks Dot
            if (completedTasksBadge) {
                completedTasksBadge.style.display = (!completedTasksTabVisible && completedTasksBadge.style.display === 'inline-block') ? 'inline-block' : 'none';
            }
        }

        // Close dropdown when clicking outside
        window.addEventListener('click', function(e) {
            const dropdown = document.getElementById('notifDropdown');
            const bell = document.getElementById('notifBell');
            if (dropdown && !dropdown.contains(e.target) && !bell.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });

        // Initialize notifications on load
        document.addEventListener('DOMContentLoaded', function() {
            loadNotifications();
            updateNotifUI();
            
            // Create notification container if not exists
            if (!document.querySelector('.notification-container')) {
                const notifContainer = document.createElement('div');
                notifContainer.className = 'notification-container';
                document.body.appendChild(notifContainer);
            }
        });
    
