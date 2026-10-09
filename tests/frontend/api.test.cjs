const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../frontend/js/api.js'), 'utf8');

function client(fetch) {
  const data = new Map([['token', 'old-access'], ['refresh', 'old-refresh'], ['user', '{}'], ['wizdesk-theme', 'dark']]);
  const timers = new Map(); let id = 0;
  const redirects = [];
  const localStorage = {getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key)};
  const location = {origin: 'http://localhost', pathname: '/leader-dashboard.html', assign: url => redirects.push(url)};
  const document = {visibilityState: 'visible'};
  const window = {fetch, addEventListener() {}};
  const context = {window, localStorage, location, document, navigator: {}, Request, Response, Headers, URL, AbortSignal,
    setTimeout: (fn, delay) => {const timer = ++id; timers.set(timer, {fn: async () => {timers.delete(timer); await fn();}, delay}); return timer;}, clearTimeout: timer => timers.delete(timer)};
  vm.runInNewContext(source, context);
  return {api: window.WizDeskAPI, fetch: window.fetch, data, timers, document, redirects};
}
const json = (value, status = 200) => new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json'}});

test('simultaneous 401s share refresh and store both rotated tokens', async () => {
  let refreshes = 0;
  const app = client(async (url, options) => {
    if (url.includes('token/refresh')) {refreshes++; await new Promise(resolve => setImmediate(resolve)); return json({access: 'new-access', refresh: 'new-refresh'});}
    return options.headers.get('Authorization') === 'Bearer old-access' ? json({}, 401) : json({ok: true});
  });
  const responses = await Promise.all([app.fetch('/api/tasks/'), app.fetch('/api/auth/me/')]);
  assert.ok(responses.every(response => response.ok));
  assert.equal(refreshes, 1);
  assert.equal(app.data.get('refresh'), 'new-refresh');
  assert.equal(app.data.get('token'), 'new-access');
});

test('two successive expiry cycles use the newly rotated refresh', async () => {
  const submitted = []; let version = 0;
  const app = client(async (url, options) => {
    if (url.includes('token/refresh')) {
      submitted.push(JSON.parse(options.body).refresh); version++;
      return json({access: `access-${version}`, refresh: `refresh-${version}`});
    }
    return options.headers.get('Authorization') === `Bearer access-${version}` && version ? json({}) : json({}, 401);
  });
  await app.fetch('/api/tasks/');
  app.data.set('token', 'expired-again');
  await app.fetch('/api/tasks/');
  assert.deepEqual(submitted, ['old-refresh', 'refresh-1']);
});

test('failed refresh rejects every waiting request and clears only session keys', async () => {
  const app = client(async () => {await new Promise(resolve => setImmediate(resolve)); return json({}, 401);});
  const settled = await Promise.allSettled([app.fetch('/api/tasks/'), app.fetch('/api/auth/me/')]);
  assert.ok(settled.every(result => result.status === 'rejected'));
  assert.equal(app.data.get('token'), undefined);
  assert.equal(app.data.get('refresh'), undefined);
  assert.equal(app.data.get('user'), undefined);
  assert.equal(app.data.get('wizdesk-theme'), 'dark');
});

test('temporary refresh failure retains the session for retry', async () => {
  const app = client(async url => json({}, url.includes('refresh') ? 503 : 401));
  await assert.rejects(app.fetch('/api/tasks/'), /retry/);
  assert.equal(app.data.get('refresh'), 'old-refresh');
});

test('public authentication requests and external URLs do not receive session headers', async () => {
  const seen = [];
  const app = client(async (url, options) => {seen.push(options?.headers?.get?.('Authorization')); return json({}, 401);});
  assert.equal((await app.fetch('/api/auth/login/', {method: 'POST'})).status, 401);
  await app.fetch('https://example.com/data');
  assert.deepEqual(seen, [null, undefined]);
});

test('pagination follows every same-origin page and rejects external next links', async () => {
  const app = client(async url => String(url).includes('page=2') ? json({results: [2], next: null}) : json({results: [1], next: '/api/tasks/?page=2'}));
  assert.deepEqual(Array.from(await (await app.fetch('/api/tasks/')).json()), [1, 2]);
  const bad = client(async () => json({results: [1], next: 'https://example.com/api/tasks/'}));
  await assert.rejects((await bad.fetch('/api/tasks/')).json(), /pagination/);
});

test('logout revokes the stored refresh and prevents a late refresh from restoring the session', async () => {
  let completeRefresh; let submitted;
  const app = client(async (url, options) => {
    if (url.includes('token/refresh')) return new Promise(resolve => {completeRefresh = resolve;});
    if (url.includes('logout')) {submitted = JSON.parse(options.body).refresh; return new Response(null, {status: 204});}
    return json({}, 401);
  });
  const pending = app.fetch('/api/tasks/');
  await new Promise(resolve => setImmediate(resolve));
  await app.api.logout();
  completeRefresh(json({access: 'late', refresh: 'late-refresh'}));
  await assert.rejects(pending, /expired/);
  assert.equal(submitted, 'old-refresh');
  assert.equal(app.data.get('token'), undefined);
});

test('polling waits for completion, skips hidden tabs and backs off on failure', async () => {
  const app = client(async () => json({}, 429));
  let calls = 0, finish;
  app.api.poll(async () => {calls++; await new Promise(resolve => {finish = resolve;}); await app.fetch('/api/tasks/');});
  const [{fn, delay}] = app.timers.values();
  assert.equal(delay, 60000);
  const ticking = fn();
  assert.equal(app.timers.size, 0);
  finish(); await ticking;
  assert.equal([...app.timers.values()][0].delay, 120000);
  app.document.visibilityState = 'hidden';
  await [...app.timers.values()][0].fn();
  assert.equal(calls, 1);
  await app.api.logout();
  assert.equal(app.timers.size, 0);
});

test('datetime-local round trips preserve the instant in a non-UTC timezone', () => {
  const app = client(async () => json({}));
  const value = '2030-02-01T04:30:00.000Z';
  assert.equal(app.api.toUTC(app.api.toLocalInput(value)), value);
});

test('polling grows its interval with request/page count', async () => {
  const app = client(async () => json({}));
  app.api.poll(async () => {for (let index = 0; index < 10; index++) await app.fetch('/api/tasks/');});
  await [...app.timers.values()][0].fn();
  assert.equal([...app.timers.values()][0].delay, 72000);
});

test('all frontend scripts parse and every template asset points to an existing file', () => {
  const root = path.join(__dirname, '../../frontend');
  for (const file of fs.readdirSync(path.join(root, 'js'))) {
    if (file.endsWith('.js')) new vm.Script(fs.readFileSync(path.join(root, 'js', file), 'utf8'), {filename: file});
  }
  for (const file of fs.readdirSync(root).filter(file => file.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) new vm.Script(match[1], {filename: file});
    for (const match of html.matchAll(/{% static '([^']+)' %}/g)) assert.ok(fs.existsSync(path.join(root, match[1])), `${file}: ${match[1]}`);
  }
});
