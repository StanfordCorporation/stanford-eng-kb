import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy matches prod: FastAPI owns the full /api/* path, no rewrite.
    // Run the backend locally with:  uvicorn api.index:app --reload --port 8000
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
