/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // In production CloudFront serves /api on the same origin. For local dev, point the
  // proxy at a deployed API: VITE_API_PROXY=https://<api-id>.execute-api.us-east-1.amazonaws.com
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      proxy: env.VITE_API_PROXY
        ? { '/api': { target: env.VITE_API_PROXY, changeOrigin: true } }
        : undefined,
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      globals: true,
    },
  }
})
