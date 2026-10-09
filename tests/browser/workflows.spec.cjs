const {test, expect} = require('@playwright/test');

async function login(page, role) {
  await page.goto('/');
  if (role === 'member') await page.locator('#tab-member').click();
  await page.locator(`#${role}Email`).fill(`${role}@example.com`);
  await page.locator(`#${role}Password`).fill('OceanWaves!2031');
  await page.locator(`#${role}TeamCode`).fill('BROWSE');
  await page.locator(`#${role}LoginForm button[type=submit]`).click();
  await expect(page).toHaveURL(new RegExp(`${role}-dashboard`));
  await expect(page.locator('#teamCodeDisplay')).toHaveText('BROWSE');
}

test('leader dashboard loads all pages and slash aliases resolve assets', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page, 'leader');
  await expect.poll(() => page.evaluate(() => allTasks.length)).toBeGreaterThanOrEqual(25);
  await page.goto('/leader-dashboard/');
  await expect(page.locator('#teamCodeDisplay')).toHaveText('BROWSE');
  await expect.poll(() => page.evaluate(() => allTasks.length)).toBeGreaterThanOrEqual(25);
  expect(errors).toEqual([]);
});

test('edit modal renders hostile text safely and saves additions and removals together', async ({page}) => {
  await login(page, 'leader');
  await expect.poll(() => page.evaluate(() => allTasks.length)).toBeGreaterThanOrEqual(25);
  const id = await page.evaluate(async () => {
    const response = await fetch('/api/tasks/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
      title: 'Hostile editor fixture', subtasks: [{title: '<img src=x onerror="window.__xss=true">',
        description: '</textarea><img src=x onerror="window.__xss=true">', deadline: '2030-02-01T04:30:00Z'}]
    })});
    return (await response.json()).id;
  });
  await page.evaluate(taskId => editTask(taskId), id);
  const modal = page.locator('#editTaskModal');
  await expect(modal).toBeVisible();
  await expect(modal).toHaveAttribute('role', 'dialog');
  await expect(modal.locator('.edit-subtask-input')).toHaveValue('<img src=x onerror="window.__xss=true">');
  await expect(modal.locator('.edit-subtask-desc')).toHaveValue('</textarea><img src=x onerror="window.__xss=true">');
  await expect(modal.locator('.edit-subtask-deadline')).toHaveValue('2030-02-01T10:00');
  await expect(modal.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();
  await modal.getByRole('button', {name: 'Remove', exact: true}).click();
  await modal.getByRole('button', {name: 'Add subtask', exact: true}).click();
  await modal.getByLabel('Subtask title', {exact: true}).fill('Added in browser');
  await modal.getByLabel('Subtask deadline', {exact: true}).fill('2030-02-02T10:00');
  await modal.getByRole('button', {name: 'Update Task', exact: true}).click();
  await expect(modal).toBeHidden();
  const task = await page.evaluate(async taskId => (await fetch(`/api/tasks/${taskId}/`)).json(), id);
  expect(task.subtasks).toHaveLength(1);
  expect(task.subtasks[0].title).toBe('Added in browser');
  expect(task.subtasks[0].deadline).toBe('2030-02-02T04:30:00Z');
});

test('member groups equal task titles separately and logout removes credentials', async ({page, request}) => {
  await login(page, 'member');
  const memberId = await page.evaluate(() => JSON.parse(localStorage.getItem('user')).id);
  const leader = await (await request.post('/api/auth/login/', {data: {email: 'leader@example.com', password: 'OceanWaves!2031'}})).json();
  const headers = {Authorization: `Bearer ${leader.token}`};
  for (let index = 0; index < 2; index++) {
    const response = await request.post('/api/tasks/', {headers, data: {title: 'Independent Equal Title', subtasks: [{title: `Group ${index}`, assigned_to: memberId}]}});
    expect(response.status()).toBe(201);
  }
  const assigned = await (await request.get(`/api/tasks/user/${memberId}/subtasks/`, {headers})).json();
  await page.locator('[data-tab="assigned-tasks"]').click();
  await expect(page.locator('#assignedTasksList .task-card')).toHaveCount(assigned.count);
  await expect(page.locator('#assignedTasksList .task-title', {hasText: 'Independent Equal Title'})).toHaveCount(2);
  await page.locator('#logoutBtn').click();
  await expect(page.locator('#confirmationModal')).toBeVisible();
  await page.locator('#confirmAction').click();
  await expect(page).toHaveURL(/index.html/);
  expect(await page.evaluate(() => ['token', 'refresh', 'user'].map(key => localStorage.getItem(key)))).toEqual([null, null, null]);
});

test('dialog traps keyboard focus and Escape returns focus to the trigger', async ({page}) => {
  await login(page, 'leader');
  const button = page.locator('#logoutBtn');
  await button.click();
  const dialog = page.getByRole('dialog', {name: 'Confirm Logout'});
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.locator('#confirmLogout')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(button).toBeFocused();
});

test('verification link errors are shown and resend remains accessible', async ({page}) => {
  await page.goto('/register-leader.html?uid=bad&token=bad');
  await expect(page).toHaveURL(/register-leader.html$/);
  await expect(page.getByText(/Invalid or expired verification link/)).toBeVisible();
  await page.getByLabel('Email address for verification').fill('unknown@example.com');
  await page.getByRole('button', {name: 'Resend verification email'}).click();
  await expect(page.getByText('If eligible, a verification email will arrive.', {exact: true})).toBeVisible();
});

test('editing completed work preserves its former member assignment', async ({page}) => {
  await login(page, 'leader');
  await expect.poll(() => page.evaluate(() => allTasks.length)).toBeGreaterThanOrEqual(25);
  const original = await page.evaluate(() => allTasks.find(task => task.title === 'Historical assignment'));
  await page.evaluate(id => editTask(id), original.id);
  const modal = page.locator('#editTaskModal');
  await expect(modal).toBeVisible();
  await expect(modal.getByLabel('Assignee')).toHaveValue(original.subtasks[0].assigned_to);
  await modal.locator('#editTaskDescription').fill('Unrelated edit preserves history');
  await modal.getByRole('button', {name: 'Update Task', exact: true}).click();
  await expect(modal).toBeHidden();
  const task = await page.evaluate(async id => (await fetch(`/api/tasks/${id}/`)).json(), original.id);
  expect(task.subtasks[0].assigned_to).toBe(original.subtasks[0].assigned_to);
  expect(task.subtasks[0].progress).toBe('completed');
  expect(task.status).toBe('completed');
});
