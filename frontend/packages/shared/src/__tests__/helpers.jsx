// Shared test helpers. Components read the store through useStore(); each test file replaces that hook with
// vi.mock('../StoreApp.jsx') and sets `store.value` to one of these synthetic contexts. No network, no backend.
import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi } from 'vitest';
import { ApiError } from '../api.js';

// The two stores' configs, mirroring apps/store-a and apps/store-b (names, assistants, suggestions).
export const STORE_CONFIGS = {
  'store-a': {
    storeId: 'store-a', name: 'Summit Trail Co.', assistantName: 'Scout', art: {}, productImages: {},
    suggestions: {
      ta: ['உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?'],
      en: ['Do you have a 2-person tent?'],
      hi: ['क्या आपके पास दो लोगों का टेंट है?'],
    },
  },
  'store-b': {
    storeId: 'store-b', name: 'Bloom & Brew', assistantName: 'Maple', art: {}, productImages: {},
    suggestions: {
      ta: ['உங்களிடம் என்ன காபி பீன்ஸ் உள்ளன?'],
      en: ['Which coffee beans do you have?'],
      hi: ['आपके पास कौन-सी कॉफ़ी बीन्स हैं?'],
    },
  },
};

export const CUSTOMER = { customer: { name: 'Test Shopper', role: 'customer' } };

export function makeApi(overrides = {}) {
  return {
    order: vi.fn(), paymentStatus: vi.fn(), startPayment: vi.fn(), completeSandboxPayment: vi.fn(), verifyPayment: vi.fn(),
    cancelOrder: vi.fn(), quote: vi.fn(), checkout: vi.fn(), chat: vi.fn(), addToCart: vi.fn(),
    speechCapabilities: vi.fn().mockResolvedValue({}), synthesize: vi.fn(), transcribe: vi.fn(),
    ...overrides,
  };
}

export function makeStore({ storeId = 'store-a', session = CUSTOMER, api = makeApi(), deliveryCountry = null } = {}) {
  return { api, session, config: STORE_CONFIGS[storeId], notify: vi.fn(), info: null, openChat: vi.fn(),
    deliveryCountry, setDeliveryCountry: vi.fn() };
}

export const apiError = (message, status, code, details) => new ApiError(message, status, code, details);

// A promise the test resolves or rejects when it chooses (to observe in-flight states).
export function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname}{loc.search}</div>;
}

/** Render `element` at `path` (matching `route`), with a probe showing where navigation went. */
export function renderAt(element, { path = '/', route = '*' } = {}) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path={route} element={<>{element}<LocationProbe /></>} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}
