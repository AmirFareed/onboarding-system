import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite configuration for the FinTech frontend. The React plugin enables the
// modern JSX transform; CSS Modules work out of the box for *.module.css files.
// The dev server proxies /api/v1 to the FastAPI backend so the browser never
// hits CORS in development (the backend has no CORS middleware configured).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
