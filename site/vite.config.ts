import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The server's CORS list, SITE_URL and the tray's Recalibrate all expect
    // 5173; fail loudly instead of quietly moving to 5174.
    port: 5173,
    strictPort: true,
    // Account pages call /api on this origin so the httpOnly session cookie
    // is first-party. The calibration page still calls 127.0.0.1:8000 directly.
    proxy: {
      '/api': { target: process.env.IRISCLICK_API_TARGET ?? 'http://127.0.0.1:8000' },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
})
