import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api/v1/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
