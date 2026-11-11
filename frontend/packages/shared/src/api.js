// Thin REST client bound to one store. The store id is fixed per storefront build;
// the backend re-validates it and the session token on every request.
//
// Storage (all keys are per store, so the two storefronts never share anything):
//  - session token: sessionStorage (cleared when the tab closes; revoked on the server at sign-out)
//  - guest cart token: localStorage (an opaque id only — prices and contents live on the server)

export class ApiError extends Error {
  constructor(message, status, code, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const SESSION_EVENT = 'avc-session-change';
export const CART_EVENT = 'avc-cart-change';

export function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID().replace(/-/g, '');
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function createApi(storeId) {
  const base = `/api/stores/${storeId}`;
  const key = `avc:${storeId}:session`;
  const cartKey = `avc:${storeId}:cart-token`;

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
  const cartToken = () => {
    try {
      return localStorage.getItem(cartKey);
    } catch {
      return null;
    }
  };
  const setCartToken = (t) => {
    try {
      if (t) localStorage.setItem(cartKey, t);
      else localStorage.removeItem(cartKey);
    } catch {
      /* guest cart lasts for this page only */
    }
  };
  const cartChanged = (cart) => {
    window.dispatchEvent(new CustomEvent(CART_EVENT, { detail: cart }));
    return cart;
  };

  async function request(path, { method = 'GET', body, headers: extra = {} } = {}) {
    const headers = { Accept: 'application/json', ...extra };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const session = loadSession();
    if (session?.token) headers.Authorization = `Bearer ${session.token}`;
    // Cookie sessions (server AUTH_COOKIES=true): the browser sends the HttpOnly cookie itself; state-changing requests
    // carry the CSRF token the server gave at sign-in (double-submit). The session token is never visible here.
    if (session?.cookie && method !== 'GET' && method !== 'HEAD') headers['X-CSRF-Token'] = session.csrf;
    const guest = cartToken();
    if (guest && !session) headers['X-Cart-Token'] = guest;
    let res;
    try {
      res = await fetch(path.startsWith('/api/') ? path : base + path, {
        method,
        headers,
        credentials: 'same-origin',
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError('Cannot reach the server. Please check that the backend is running.', 0, 'network');
    }
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      if (res.status === 401 && session) saveSession(null);
      throw new ApiError(data?.error?.message || `Request failed (${res.status})`, res.status, data?.error?.code, data?.error?.details);
    }
    return data;
  }

  async function startSession(data) {
    // Move anything the shopper added as a guest into their account cart BEFORE announcing the
    // session, so pages that react to sign-in (e.g. checkout) already see the merged cart.
    const cookieMode = data.token_type === 'cookie';
    const guest = cartToken();
    if (guest && data.customer.role === 'customer') {
      try {
        const auth = cookieMode ? { 'X-CSRF-Token': data.csrf_token } : { Authorization: `Bearer ${data.access_token}` };
        await request('/cart/merge', { method: 'POST', headers: { ...auth, 'X-Cart-Token': guest } });
        setCartToken(null);
      } catch {
        /* keep the guest token; merge can be retried on next sign-in */
      }
    }
    saveSession(cookieMode
      ? { cookie: true, csrf: data.csrf_token, customer: data.customer, expiresAt: Date.now() + data.expires_in * 1000 }
      : { token: data.access_token, customer: data.customer, expiresAt: Date.now() + data.expires_in * 1000 });
    return data.customer;
  }

  return {
    storeId,
    loadSession,
    store: (lang) => request(lang && lang !== 'en' ? `?lang=${encodeURIComponent(lang)}` : ''),
    market: () => request('/market'),
    categories: () => request('/categories'),
    products: ({ q, category } = {}) => {
      const p = new URLSearchParams();
      if (q) p.set('q', q);
      if (category) p.set('category', category);
      const qs = p.toString();
      return request(`/products${qs ? `?${qs}` : ''}`);
    },
    product: (slug) => request(`/products/${encodeURIComponent(slug)}`),

    // ---- accounts
    login: async (email, password) => startSession(await request('/auth/login', { method: 'POST', body: { email, password } })),
    register: async (fullName, email, password) =>
      startSession(await request('/auth/register', { method: 'POST', body: { full_name: fullName, email, password } })),
    async logout() {
      try {
        if (loadSession()) await request('/auth/logout', { method: 'POST' });
      } catch {
        /* the local session is cleared regardless */
      }
      saveSession(null);
      cartChanged(null);
    },
    requestPasswordReset: (email) => request('/auth/password-reset/request', { method: 'POST', body: { email } }),
    confirmPasswordReset: (token, newPassword) =>
      request('/auth/password-reset/confirm', { method: 'POST', body: { token, new_password: newPassword } }),

    // ---- orders
    myOrders: () => request('/orders'),
    order: (number) => request(`/orders/${encodeURIComponent(number)}`),
    adminOrders: () => request('/admin/orders'),

    // ---- staff fulfilment (agent accounts only; the server enforces it)
    staffOrders({ status = [], q = '', limit = 25, offset = 0 } = {}) {
      const params = new URLSearchParams();
      status.forEach((s) => params.append('status', s));
      if (q) params.set('q', q);
      params.set('limit', String(limit));
      params.set('offset', String(offset));
      return request(`/staff/orders?${params}`);
    },
    staffOrder: (number) => request(`/staff/orders/${encodeURIComponent(number)}`),
    staffAction: (number, action, body) =>
      request(`/staff/orders/${encodeURIComponent(number)}/${action}`, { method: 'POST', body }),
    staffTracking: (number, body) => request(`/staff/orders/${encodeURIComponent(number)}/tracking`, { method: 'PUT', body }),

    // ---- customer care: complaints, returns, simulated refunds, human help (the server enforces every rule)
    careOptions: (kind, order) => request(`/care/options?kind=${encodeURIComponent(kind)}${order ? `&order=${encodeURIComponent(order)}` : ''}`),
    careCreate: (body, idempotencyKey) => request('/care/requests', { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body }),
    careRequests: () => request('/care/requests'),
    careRequest: (ref) => request(`/care/requests/${encodeURIComponent(ref)}`),
    careReply: (ref, message) => request(`/care/requests/${encodeURIComponent(ref)}/reply`, { method: 'POST', body: { message } }),
    careWithdraw: (ref) => request(`/care/requests/${encodeURIComponent(ref)}/withdraw`, { method: 'POST' }),
    staffCare({ kind = [], status = [], q = '', dateFrom = '', dateTo = '', limit = 25, offset = 0 } = {}) {
      const p = new URLSearchParams();
      kind.forEach((k) => p.append('kind', k));
      status.forEach((s) => p.append('status', s));
      if (q) p.set('q', q);
      if (dateFrom) p.set('date_from', dateFrom);
      if (dateTo) p.set('date_to', dateTo);
      p.set('limit', String(limit));
      p.set('offset', String(offset));
      return request(`/staff/care?${p}`);
    },
    staffCareRequest: (ref) => request(`/staff/care/${encodeURIComponent(ref)}`),
    staffCareAgents: () => request('/staff/care/agents'),
    staffCareStatus: (ref, body) => request(`/staff/care/${encodeURIComponent(ref)}/status`, { method: 'POST', body }),
    staffCareAssign: (ref, assigneeId) => request(`/staff/care/${encodeURIComponent(ref)}/assign`, { method: 'POST', body: { assignee_id: assigneeId } }),
    staffCareNote: (ref, body) => request(`/staff/care/${encodeURIComponent(ref)}/notes`, { method: 'POST', body: { body } }),
    staffCareMessage: (ref, body) => request(`/staff/care/${encodeURIComponent(ref)}/messages`, { method: 'POST', body: { body } }),

    // ---- cart (server computes every price and total)
    // country (delivery country) → prices in its currency; omitted = the catalogue prices and US rates, as before
    cart: async (country) => (await request(country ? `/cart?country=${encodeURIComponent(country)}` : '/cart')).cart,
    async addToCart(slug, quantity = 1) {
      const r = await request('/cart/items', { method: 'POST', body: { slug, quantity } });
      if (r.cart_token) setCartToken(r.cart_token);
      return cartChanged(r.cart);
    },
    updateCartItem: async (slug, quantity) =>
      cartChanged((await request(`/cart/items/${encodeURIComponent(slug)}`, { method: 'PUT', body: { quantity } })).cart),
    removeCartItem: async (slug) => cartChanged((await request(`/cart/items/${encodeURIComponent(slug)}`, { method: 'DELETE' })).cart),

    // ---- checkout & payments
    // destination omitted = the store's US rates (the request older servers understand)
    quote: async (shippingMethod, destination) => (await request('/checkout/quote', { method: 'POST',
      body: { shipping_method: shippingMethod, ...(destination ? { destination } : {}) } })).cart,
    addressOptions: () => request('/checkout/address-options'),
    async checkout({ shipping, shippingMethod, expectedTotalCents, idempotencyKey }) {
      const r = await request('/checkout', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: { shipping, shipping_method: shippingMethod, expected_total_cents: expectedTotalCents },
      });
      cartChanged(null);
      return r;
    },
    cancelOrder: (number) => request(`/orders/${encodeURIComponent(number)}/cancel`, { method: 'POST' }),
    paymentStatus: (number) => request(`/orders/${encodeURIComponent(number)}/payment`),
    startPayment: (number) => request(`/orders/${encodeURIComponent(number)}/payments`, { method: 'POST' }),
    verifyPayment: (number) => request(`/orders/${encodeURIComponent(number)}/payments/verify`, { method: 'POST' }),
    completeSandboxPayment: (reference, outcome) =>
      request(`/payments/sandbox/${encodeURIComponent(reference)}/complete`, { method: 'POST', body: { outcome } }),

    // conversationLanguage only decides language-neutral messages; speechReceipt carries the server's own
    // acoustic detection; languageOverride is an explicit customer choice (never sent as "detection").
    chat: (message, history, channel = 'web_chat', { conversationLanguage, speechReceipt, languageOverride, careDraft } = {}) =>
      request('/chat', {
        method: 'POST',
        body: {
          message, history, channel,
          ...(conversationLanguage && { conversation_language: conversationLanguage }),
          ...(speechReceipt && { speech_receipt: speechReceipt }),
          ...(languageOverride && { language_override: languageOverride }),
          ...(careDraft && { care_draft: careDraft }),
        },
      }),
    speechCapabilities: () => request('/api/speech/capabilities'),
    // Simulated customer-care phone line (no telephone network): the real call flow over text turns.
    phoneStart: (language) => request(`/api/phone/simulator/${storeId}/calls`, { method: 'POST', body: language ? { language } : {} }),
    phoneTurn: (callId, { speech, digits } = {}) => request(`/api/phone/simulator/calls/${encodeURIComponent(callId)}/turns`, {
      method: 'POST', body: { ...(speech !== undefined && { speech }), ...(digits !== undefined && { digits }) },
    }),
    async synthesize(text, language) {
      const res = await fetch('/api/speech/synthesize', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language }),
      });
      if (!res.ok) throw new ApiError('Server speech is unavailable.', res.status);
      return res.blob();
    },
    // Returns { text, language, detected_language, language_probability, used_default }.
    async transcribe(wavBlob, language = 'auto') {
      let res;
      try {
        res = await fetch(`${base}/speech/transcribe?language=${encodeURIComponent(language)}`, {
          method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wavBlob,
        });
      } catch {
        throw new ApiError('Cannot reach the server for voice input. Please type your question.', 0, 'network');
      }
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new ApiError(data?.error?.message || 'Voice input failed.', res.status, data?.error?.code);
      return { ...data, text: data.text || '' };
    },
  };
}
