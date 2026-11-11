#!/usr/bin/env node
// Mutation checks for the mobile / accessibility / keyboard layers: proves the tests FAIL when a representative
// defect is introduced. Each defect is applied to a TEMPORARY COPY of the Store A app and the shared package
// (frontend/.mutation-tmp/, removed afterwards); the live source files are never modified. The copy is built into
// its own folder and served on the isolated port 15180 through AVC_E2E_DIST_STORE_A (see playwright.config.cjs).
//
// Usage (from frontend/):  node e2e/mutations/run.cjs [mutation-id ...]
const { execFileSync, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const FRONTEND = path.resolve(__dirname, '..', '..');
const TMP = path.join(FRONTEND, '.mutation-tmp');

const MUTATIONS = [
  { id: 'wide-element', what: 'a product grid wider than a phone screen (page-level horizontal overflow)',
    file: 'shared/src/styles.css', find: '  .product-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }',
    replace: '  .product-grid { grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 12px; }',
    tests: ['mobile', '-g', 'small-mobile.*home page'] },
  { id: 'missing-label', what: 'the cart quantity <select> loses its label',
    file: 'shared/src/pages/CartPage.jsx', find: '<label className="sr-only" htmlFor={`qty-${i.slug}`}>Quantity for {i.name}</label>', replace: '',
    tests: ['a11y', '-g', 'cart'] },
  { id: 'missing-name', what: 'the icon-only chat close button loses its accessible name',
    file: 'shared/src/ChatWidget.jsx', find: 'onClick={closeByUser} aria-label={t(\'close\')}>✕</button>', replace: 'onClick={closeByUser}><span aria-hidden="true">✕</span></button>',
    tests: ['a11y', '-g', 'AI chat'] },
  { id: 'not-keyboard', what: 'the chat launcher becomes a clickable <div> (not keyboard-focusable)',
    file: 'shared/src/ChatWidget.jsx',
    find: '<button type="button" ref={launcherRef} className="chat-launcher" onClick={onOpen} aria-label={`Open chat with ${config.assistantName}`}>\n        <span aria-hidden="true">💬</span> <span className="launcher-label">Ask {config.assistantName}</span>\n      </button>',
    replace: '<div ref={launcherRef} className="chat-launcher" onClick={onOpen} aria-label={`Open chat with ${config.assistantName}`}>\n        <span aria-hidden="true">💬</span> <span className="launcher-label">Ask {config.assistantName}</span>\n      </div>',
    tests: ['keyboard', '-g', 'Tab and Shift|chat can be'] },
  { id: 'dialog-focus', what: 'opening the chat dialog no longer moves focus into it',
    file: 'shared/src/ChatWidget.jsx', find: 'setTimeout(() => inputRef.current?.focus(), 0);', replace: '/* focus not moved */',
    tests: ['keyboard', '-g', 'chat can be|full-screen chat'] },
  { id: 'no-focus-ring', what: 'the global focus indicator is removed',
    file: 'shared/src/styles.css', find: ':focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }', replace: ':focus-visible { outline: none; }',
    tests: ['keyboard', '-g', 'Tab and Shift'] },
  { id: 'low-contrast', what: 'light-theme accent lightened so white button text fails contrast',
    file: 'store-a/src/theme.css', find: '--accent: #c2410c;', replace: '--accent: #fb923c;',
    tests: ['a11y', '-g', 'product detail'] },
  // Phase D: each fix reverted in the copy must be caught by its regression test.
  { id: 'revert-A-1', what: 'Store A dark accent back to #ea580c (3.55:1)',
    file: 'store-a/src/theme.css', find: '--brand: #234f3c; --accent: #c2410c;', replace: '--brand: #234f3c; --accent: #ea580c;',
    tests: ['a11y', '-g', 'product detail|supplementary'] },
  { id: 'revert-K-1', what: 'scroll padding for the sticky header removed',
    file: 'shared/src/styles.css', find: 'html { -webkit-text-size-adjust: 100%; scroll-padding-top: 6rem; }', replace: 'html { -webkit-text-size-adjust: 100%; }',
    // The behavioural Shift+Tab test depends on page layout; the direct assertion (padding > header height, mobile
    // home test) is what reliably guards K-1, so both run.
    tests: ['keyboard', 'mobile', '-g', 'Shift\\+Tab never|home page and main navigation'] },
  { id: 'revert-K-2', what: 'Escape handler removed from the chat',
    file: 'shared/src/ChatWidget.jsx', find: ' onKeyDown={onPanelKeyDown}', replace: '',
    tests: ['keyboard', '-g', 'chat can be'] },
  { id: 'revert-K-3', what: 'focus no longer returned when the chat closes',
    file: 'shared/src/ChatWidget.jsx', find: '      target?.focus();', replace: '',
    tests: ['keyboard', '-g', 'chat can be'] },
  { id: 'revert-K-4', what: 'full-screen chat no longer makes the page inert',
    file: 'shared/src/ChatWidget.jsx', find: 'others.forEach((el) => { el.inert = true; });', replace: '',
    tests: ['keyboard', '-g', 'full-screen chat is modal'] },
  { id: 'revert-K-5', what: 'focus no longer moved into the cancel confirmation',
    file: 'shared/src/pages/PaymentPage.jsx', find: 'if (confirmCancel) confirmRef.current?.focus();', replace: 'if (confirmCancel) { /* no focus */ }',
    tests: ['keyboard', '-g', 'keyboard alone'] },
  { id: 'revert-M-1', what: 'narrow-form layout for the checkout address row removed',
    file: 'shared/src/styles.css', find: '.checkout-form { container-type: inline-size; }', replace: '',
    tests: ['mobile', '-g', 'every width|tablet.*checkout steps'] },
];

function copyTree() {
  fs.rmSync(TMP, { recursive: true, force: true });
  fs.mkdirSync(TMP, { recursive: true });
  fs.cpSync(path.join(FRONTEND, 'packages', 'shared'), path.join(TMP, 'shared'), { recursive: true, filter: (s) => !s.includes('__tests__') });
  fs.cpSync(path.join(FRONTEND, 'apps', 'store-a'), path.join(TMP, 'store-a'), { recursive: true, filter: (s) => !s.includes(`${path.sep}dist`) && !s.includes('node_modules') });
  // Build config for the copy: '@avc/shared' resolves to the copied package instead of the live one.
  fs.writeFileSync(path.join(TMP, 'vite.mutation.config.mjs'), `
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
const here = ${JSON.stringify(TMP)};
export default defineConfig({
  root: path.join(here, 'store-a'),
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom', 'react-router-dom'], alias: [
    { find: '@avc/shared/styles.css', replacement: path.join(here, 'shared/src/styles.css') },
    { find: '@avc/shared', replacement: path.join(here, 'shared/src/index.js') } ] },
  build: { outDir: path.join(here, 'dist'), emptyOutDir: true },
  logLevel: 'warn',
});
`);
}

function apply(m) {
  const file = path.join(TMP, m.file);
  const src = fs.readFileSync(file, 'utf8');
  if (!src.includes(m.find)) throw new Error(`mutation ${m.id}: pattern not found in ${m.file} (source changed? update the mutation)`);
  fs.writeFileSync(file, src.replace(m.find, m.replace));
}

const wanted = process.argv.slice(2);
const results = [];
try {
  for (const m of MUTATIONS.filter((x) => !wanted.length || wanted.includes(x.id))) {
    copyTree();
    apply(m);
    execFileSync('npx', ['vite', 'build', '--config', path.join(TMP, 'vite.mutation.config.mjs')], { cwd: FRONTEND, stdio: 'pipe' });
    const run = spawnSync('npx', ['playwright', 'test', ...m.tests, '--project', 'store-a', '--reporter=line'], {
      cwd: FRONTEND, encoding: 'utf8', env: { ...process.env, AVC_E2E_DIST_STORE_A: path.join(TMP, 'dist'), PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: '1' },
    });
    const out = `${run.stdout}\n${run.stderr}`.replace(/\x1b\[[0-9;]*m/g, '');
    const failed = Number((out.match(/(\d+) failed/) || [0, 0])[1]);
    const passed = Number((out.match(/(\d+) passed/) || [0, 0])[1]);
    const firstError = (out.match(/Error: [^\n]+/) || [''])[0].slice(0, 160);
    results.push({ id: m.id, what: m.what, failed, passed, detected: failed > 0, firstError });
    console.log(`${failed > 0 ? 'DETECTED ' : 'MISSED   '} ${m.id.padEnd(14)} ${failed} failed / ${passed} passed — ${m.what}\n           ${firstError}`);
  }
} finally {
  fs.rmSync(TMP, { recursive: true, force: true });
}
console.log(fs.existsSync(TMP) ? 'WARNING: temporary copy still present' : 'temporary copy removed');
process.exit(results.every((r) => r.detected) ? 0 : 1);
