import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend runs on :8000; Vite proxies /api so the browser only ever talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
