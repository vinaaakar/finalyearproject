// Browser tests against an ISOLATED stack, started here and stopped afterwards:
//   - scripts/e2e_api.py on 127.0.0.1:18000 (the *_test databases only; never migrates or resets)
//   - production builds of both storefronts served by `vite preview` on 15180 / 15181, proxying /api to 18000
// The development stack (API :8000, storefronts :5180/:5181) is never used or restarted.
// Uses the installed Google Chrome (channel 'chrome'); no Playwright browser download is needed.
// CommonJS on purpose: Playwright 1.49's ES-module config loader hangs on Node 25.
const { defineConfig } = require('@playwright/test');
const path = require('node:path');

const here = __dirname;
const root = path.resolve(here, '..');
const API_PORT = 18000;
const PORTS = { 'store-a': 15180, 'store-b': 15181 };
const apiUrl = `http://127.0.0.1:${API_PORT}`;

// AVC_E2E_DIST_STORE_A / AVC_E2E_DIST_STORE_B: serve an already-built copy instead of building the app (used only by
// the mutation checks, which build deliberately broken COPIES outside the source tree; see docs/mobile-accessibility-testing.md).
const distOverride = (app) => process.env[`AVC_E2E_DIST_${app.replace('-', '_').toUpperCase()}`];
const storefront = (app) => ({
  command: distOverride(app)
    ? `npm run preview -w ${app} -- --outDir "${distOverride(app)}" --port ${PORTS[app]} --strictPort`
    : `npm run build -w ${app} && npm run preview -w ${app} -- --port ${PORTS[app]} --strictPort`,
  cwd: here,
  env: { AVC_API_URL: apiUrl },
  url: `http://127.0.0.1:${PORTS[app]}/`,
  reuseExistingServer: false,
  timeout: 120_000,
});

module.exports = defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  globalTimeout: 1_200_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { channel: 'chrome', headless: true, trace: 'retain-on-failure' },
  outputDir: path.join(here, 'test-results'),
  globalSetup: path.join(here, 'e2e', 'support', 'prices-setup.cjs'),
  globalTeardown: path.join(here, 'e2e', 'support', 'prices-teardown.cjs'),
  projects: [
    { name: 'store-a', use: { baseURL: `http://127.0.0.1:${PORTS['store-a']}` } },
    { name: 'store-b', use: { baseURL: `http://127.0.0.1:${PORTS['store-b']}` } },
  ],
  webServer: [
    {
      command: `"${path.join(root, 'backend/.venv/bin/python')}" "${path.join(root, 'scripts/e2e_api.py')}" --port ${API_PORT}`,
      // India-only, exactly as the demo: the demonstration shipping in config/shipping/ and (globalSetup) the
      // demonstration INR price list copied into the *_test databases.
      env: { ...process.env, AVC_E2E_AUTH_COOKIES: process.env.AVC_E2E_AUTH_COOKIES || '', AVC_E2E_SPEECH: process.env.AVC_E2E_SPEECH || '' },
      cwd: root,
      url: `${apiUrl}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    storefront('store-a'),
    storefront('store-b'),
  ],
});
