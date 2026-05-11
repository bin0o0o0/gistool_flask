import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 开发服务器代理 /api 到本机 Flask，这样前端代码不需要写死后端地址。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // 和 README 中的后端启动方式对应：propy.bat backend/run.py 默认监听 5000。
      // 本机 5000 被其它项目占用时，临时改到 5001（后端通过 FLASK_PORT=5001 启动）。
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true
      }
    }
  },
  test: {
    environment: 'node'
  }
})
