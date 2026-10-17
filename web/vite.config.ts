import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// npm run dev: the app on :5173, API calls passed on to server.py on :8000
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
