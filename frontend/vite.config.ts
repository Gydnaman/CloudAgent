import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
    headers: {
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000 http://127.0.0.1:5173 http://localhost:5173"
    }
  }
})
