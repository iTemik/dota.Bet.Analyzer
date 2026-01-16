import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/statistics': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      '/stream-progress': {
        target: 'http://localhost:5000',
        changeOrigin: true
      },
      '/results': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
