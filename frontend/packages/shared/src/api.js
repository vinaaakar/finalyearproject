// Thin REST client bound to one store. The store id is fixed per storefront build;
// the backend re-validates it and the session token on every request.

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const SESSION_EVENT = 'avc-session-change';

export function createApi(storeId) {
  const base = `/api/stores/${storeId}`;
  const key = `avc:${storeId}:session`;

  const loadSession = () => {
    try {
      const s = JSON.parse(sessionStorage.getItem(key));
      return s && s.expiresAt > Date.now() ? s : null;
    } catch {
      return null;
    }
  };
  const saveSession = (s) => {
    try {
      if (s) sessionStorage.setItem(key, JSON.stringify(s));
      else sessionStorage.removeItem(key);
    } catch {
      /* storage unavailable: session lasts for this page only */
    }
    window.dispatchEvent(new Event(SESSION_EVENT));
  };

  async function request(path, { method = 'GET', body } = {}) {
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const session = loadSession();
    if (session?.token) headers.Authorization = `Bearer ${session.token}`;
    let res;
    try {
      res = await fetch(path.startsWith('/api/') ? path : base + path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError('Cannot reach the server. Please check that the backend is running.', 0, 'network');
    }
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401 && session) saveSession(null);
      throw new ApiError(data?.error?.message || `Request failed (${res.status})`, res.status, data?.error?.code);
    }
    return data;
  }

  return {
    storeId,
    loadSession,
    store: () => request(''),
    categories: () => request('/categories'),
    products: ({ q, category } = {}) => {
      const p = new URLSearchParams();
      if (q) p.set('q', q);
      if (category) p.set('category', category);
      const qs = p.toString();
      return request(`/products${qs ? `?${qs}` : ''}`);
    },
    product: (slug) => request(`/products/${encodeURIComponent(slug)}`),
    async login(email, password) {
      const data = await request('/auth/login', { method: 'POST', body: { email, password } });
      saveSession({ token: data.access_token, customer: data.customer, expiresAt: Date.now() + data.expires_in * 1000 });
      return data.customer;
    },
    logout: () => saveSession(null),
    myOrders: () => request('/orders'),
    adminOrders: () => request('/admin/orders'),
    chat: (message, history, channel = 'web_chat') => request('/chat', { method: 'POST', body: { message, history, channel } }),
    speechCapabilities: () => request('/api/speech/capabilities'),
  };
}
