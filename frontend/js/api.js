/* Shared authenticated client, pagination adapter, session lifecycle and polling. */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  let refreshPromise = null;
  let requestFailures = 0;
  let requestCount = 0;
  const timers = new Set();
  const publicPaths = ['/auth/login/', '/auth/send-', '/auth/verify-', '/auth/resend-', '/auth/config/', '/auth/check-member-status/', '/auth/logout/', '/token/refresh/'];
  const apiURL = value => {
    const url = new URL(value instanceof Request ? value.url : value, location.origin);
    return url.origin === location.origin && url.pathname.startsWith('/api/') ? url : null;
  };
  async function apiFetch(resource, options) {
    requestCount++;
    let response;
    try {response = await nativeFetch(resource, options);}
    catch (error) {requestFailures++; throw error;}
    if (response.status === 429 || response.status >= 500) requestFailures++;
    return response;
  }
  function clearSession() {
    ['token', 'refresh', 'user'].forEach(key => localStorage.removeItem(key));
    timers.forEach(clearTimeout);
    timers.clear();
  }
  function expired() {
    clearSession();
    location.assign('/index.html');
    throw new Error('Session expired. Please sign in again.');
  }
  async function rotate(oldAccess) {
    const run = async () => {
      if (localStorage.getItem('token') && localStorage.getItem('token') !== oldAccess) return localStorage.getItem('token');
      const refresh = localStorage.getItem('refresh');
      if (!refresh) return expired();
      const response = await apiFetch('/api/token/refresh/', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh}), signal: AbortSignal.timeout(10000)
      });
      if (response.status === 401 || response.status === 403) return expired();
      if (!response.ok) throw new Error('Unable to renew session. Please retry.');
      const data = await response.json();
      // Logout in another tab must not be undone by a late refresh response.
      if (localStorage.getItem('refresh') !== refresh) return expired();
      localStorage.setItem('token', data.access);
      if (data.refresh) localStorage.setItem('refresh', data.refresh);
      return data.access;
    };
    if (!refreshPromise) {
      refreshPromise = (navigator.locks ? navigator.locks.request('wizdesk-refresh', run) : run()).finally(() => {refreshPromise = null;});
    }
    return refreshPromise;
  }
  function errorMessage(data) {
    if (typeof data === 'string') return data;
    if (Array.isArray(data)) return data.map(errorMessage).join(' ');
    if (!data || typeof data !== 'object') return 'Request failed.';
    return Object.entries(data).map(([key, value]) => `${key === 'detail' ? '' : key + ': '}${errorMessage(value)}`).join(' ');
  }
  async function request(resource, options = {}) {
    const url = apiURL(resource);
    if (!url) return nativeFetch(resource, options);
    const publicRequest = publicPaths.some(path => url.pathname.startsWith('/api' + path));
    const token = localStorage.getItem('token');
    const headers = new Headers(options.headers || (resource instanceof Request ? resource.headers : undefined));
    if (token && !publicRequest) headers.set('Authorization', `Bearer ${token}`);
    const config = {...options, headers};
    let response = await apiFetch(resource, config);
    if (response.status === 401 && !publicRequest) {
      headers.set('Authorization', `Bearer ${await rotate(token)}`);
      response = await apiFetch(resource, config);
      if (response.status === 401) return expired();
    }
    const readJSON = response.json.bind(response);
    response.json = async () => {
      const data = await readJSON();
      if (!response.ok && data && typeof data === 'object' && !data.error) data.error = errorMessage(data);
      // Existing dashboards consume arrays. Follow validated same-origin pages.
      if (response.ok && Array.isArray(data.results) && Object.hasOwn(data, 'next')) {
        const results = [...data.results];
        let next = data.next;
        const seen = new Set();
        while (next) {
          const nextURL = apiURL(next);
          if (!nextURL || seen.has(nextURL.href)) throw new Error('Invalid pagination link.');
          seen.add(nextURL.href);
          const pageResponse = await request(nextURL.href, {...config, method: 'GET'});
          if (!pageResponse.ok) throw new Error(errorMessage(await pageResponse.json()));
          // Use the native JSON method to avoid recursively traversing pages.
          const page = await Response.prototype.json.call(pageResponse);
          results.push(...page.results);
          next = page.next;
        }
        return results;
      }
      return data;
    };
    return response;
  }
  function poll(callback, delay = 60000) {
    let stopped = false;
    let failures = 0;
    let timer;
    let interval = delay;
    const tick = async () => {
      timers.delete(timer);
      if (stopped || !localStorage.getItem('user')) return;
      if (document.visibilityState === 'visible') {
        const previousFailures = requestFailures;
        const previousRequests = requestCount;
        try {
          await callback();
          failures = requestFailures > previousFailures ? Math.min(failures + 1, 4) : 0;
        } catch (_) {failures = Math.min(failures + 1, 4);}
        // Reserve half the default 1,000/hour quota for interactive actions.
        interval = Math.max(delay, Math.ceil((requestCount - previousRequests) * 3600000 / 500));
      }
      if (!stopped) {timer = setTimeout(tick, interval * 2 ** failures); timers.add(timer);}
    };
    timer = setTimeout(tick, delay); timers.add(timer);
    return () => {stopped = true; clearTimeout(timer); timers.delete(timer);};
  }
  async function logout() {
    const refresh = localStorage.getItem('refresh');
    clearSession();
    try {
      if (refresh) await nativeFetch('/api/auth/logout/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh}), signal: AbortSignal.timeout(5000)});
    } finally {location.assign('/index.html');}
  }
  async function initialize(role) {
    if (!localStorage.getItem('token')) {location.assign('/index.html'); return null;}
    const response = await request('/api/auth/me/');
    if (!response.ok) throw new Error('Unable to load your account.');
    const user = await response.json();
    if (user.role.toLowerCase() !== role) return expired();
    localStorage.setItem('user', JSON.stringify(user));
    return user;
  }
  const toLocalInput = value => {
    if (!value) return '';
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  };
  window.fetch = request;
  window.WizDeskAPI = {request, poll, logout, initialize, errorMessage, toLocalInput,
    toUTC: value => value ? new Date(value).toISOString() : null};
  window.addEventListener('storage', event => {
    if (event.key === 'user' && !event.newValue && location.pathname.includes('dashboard')) {clearSession(); location.assign('/index.html');}
  });
})();
