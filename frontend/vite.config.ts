import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy to the FastAPI backend on localhost:8000 so the frontend can call
// /api/* without CORS during local development. Production reverse-proxy
// (Caddy → backend) is configured separately in docker-compose.prod.yml.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
