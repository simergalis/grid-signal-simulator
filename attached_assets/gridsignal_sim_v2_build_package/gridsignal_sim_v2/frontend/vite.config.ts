import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// FastAPI / uvicorn dev server.  Start with:
//   cd gridsignal_sim/  &&  PYTHONPATH=. uvicorn api.app:app --reload --port 8000
const API_ORIGIN = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // Allow the Replit preview iframe (proxied from a different origin).
    allowedHosts: true,
    proxy: {
      // REST endpoints — forward /runs/* to FastAPI
      '/runs': {
        target: API_ORIGIN,
        changeOrigin: true,
      },
      // WebSocket tick stream — forward /ws/* to FastAPI
      '/ws': {
        target: API_ORIGIN.replace('http://', 'ws://'),
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
