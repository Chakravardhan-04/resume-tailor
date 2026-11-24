/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // Local dev only: forward /api to a deployed API. In AWS, CloudFront does this.
  server: process.env.VITE_API_PROXY ? { proxy: { '/api': { target: process.env.VITE_API_PROXY, changeOrigin: true } } } : {},
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/setupTests.ts'] },
})
