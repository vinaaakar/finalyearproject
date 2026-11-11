import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Component tests for the shared storefront package (both stores render the same components with their own config).
// Browser tests live in e2e/ and run with Playwright, never with Vitest.
export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom', 'react-router-dom'] },
  test: {
    environment: 'jsdom',
    include: ['packages/**/*.test.{js,jsx}', 'apps/**/*.test.{js,jsx}'],
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
    setupFiles: ['./test/setup.js'],
    restoreMocks: true,
  },
});
