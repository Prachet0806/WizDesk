/* Shared authenticated client, pagination adapter, session lifecycle and polling. */
(() => {
  'use strict';
  const nativeFetch = window.fetch.bind(window);
  // Remove credentials written by the previous browser-token implementation.
  localStorage.removeItem('token');
  localStorage.removeItem('refresh');
  let refreshPromise = null;
  let requestFailures = 0;
  let requestCount = 0;
  const timers = new Set();
  const publicPaths = ['/auth/login/', '/auth/send-', '/auth/verify-', '/auth/resend-', '/auth/password-reset/', '/auth/config/', '/auth/check-member-status/', '/auth/logout/', '/token/refresh/'];
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
    localStorage.removeItem('user');
    timers.forEach(clearTimeout);
    timers.clear();
  }
  const sessionSnapshot = () => localStorage.getItem('user');
  const sameSession = snapshot => snapshot === sessionSnapshot();
  function expired(snapshot) {
    if (snapshot && !sameSession(snapshot)) throw new Error('Session changed while renewing credentials.');
    clearSession();
    location.assign('/index.html');
    throw new Error('Session expired. Please sign in again.');
  }
  function csrfToken() {
    return (document.cookie || '').split('; ').find(value => value.startsWith('csrftoken='))?.slice(10) || '';
  }
  async function rotate(snapshot) {
    const run = async () => {
      if (!sameSession(snapshot)) throw new Error('Session changed while renewing credentials.');
      const response = await apiFetch('/api/token/refresh/', {
        method: 'POST', headers: {'X-CSRFToken': csrfToken()}, signal: AbortSignal.timeout(10000)
      });
      if (response.status === 401 || response.status === 403) return expired(snapshot);
      if (!response.ok) throw new Error('Unable to renew session. Please retry.');
      if (!sameSession(snapshot)) throw new Error('Session changed while renewing credentials.');
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
    let requestSession = sessionSnapshot();
    const headers = new Headers(options.headers || (resource instanceof Request ? resource.headers : undefined));
    const method = (options.method || 'GET').toUpperCase();
    if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
      if (!csrfToken() && url.pathname !== '/api/auth/csrf/') await apiFetch('/api/auth/csrf/');
      headers.set('X-CSRFToken', csrfToken());
    }
    const config = {...options, headers};
    let response = await apiFetch(resource, config);
    if (!publicRequest && !sameSession(requestSession)) throw new Error('Session changed while the request was in progress.');
    if (response.status === 401 && !publicRequest) {
      if (!sameSession(requestSession)) throw new Error('Session changed while the request was in progress.');
      await rotate(requestSession);
      requestSession = sessionSnapshot();
      response = await apiFetch(resource, config);
      if (response.status === 401) return expired(sessionSnapshot());
      if (!sameSession(requestSession)) throw new Error('Session changed while the request was in progress.');
    }
    const readJSON = response.json.bind(response);
    response.json = async () => {
      if (!publicRequest && !sameSession(requestSession)) throw new Error('Session changed while the request was in progress.');
      const data = await readJSON();
      if (!publicRequest && !sameSession(requestSession)) throw new Error('Session changed while the request was in progress.');
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
    try { await request('/api/auth/logout/', {method: 'POST', signal: AbortSignal.timeout(5000)}); }
    finally {clearSession(); location.assign('/index.html');}
  }
  async function initialize(role) {
    await request('/api/auth/csrf/');
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
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  };
  window.fetch = request;
  window.WizDeskAPI = {request, poll, logout, initialize, errorMessage, toLocalInput,
    toUTC: (value, originalValue) => {
      if (!value) return null;
      if (originalValue) {
        const originalLocal = toLocalInput(originalValue);
        if (value === originalLocal || (originalLocal.endsWith(':00') && value === originalLocal.slice(0, 16))) return originalValue;
      }
      return new Date(value).toISOString();
    }};
  window.addEventListener('storage', event => {
    if (event.key === 'user' && !event.newValue && location.pathname.includes('dashboard')) {clearSession(); location.assign('/index.html');}
  });
})();
