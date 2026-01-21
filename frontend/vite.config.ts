import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/version': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      '/api/statistics': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      '/api/stream-progress': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      '/api/results': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
