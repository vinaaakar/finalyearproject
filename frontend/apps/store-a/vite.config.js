import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The browser talks only to this origin; /api is proxied to the central FastAPI backend.
const apiProxy = { '/api': { target: process.env.AVC_API_URL || 'http://127.0.0.1:8000', changeOrigin: false } };

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom', 'react-router-dom'] },
  server: { port: 5180, strictPort: true, host: '127.0.0.1', proxy: apiProxy },
  preview: { port: 5180, strictPort: true, host: '127.0.0.1', proxy: apiProxy },
});
