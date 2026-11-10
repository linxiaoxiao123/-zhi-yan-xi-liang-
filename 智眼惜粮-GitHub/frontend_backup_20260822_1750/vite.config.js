// vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  // 新增：定义Vue编译标志，解决警告
  define: {
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
    __VUE_OPTIONS_API__: 'true',
    __VUE_PROD_DEVTOOLS__: 'false'
  },
  // 配置跨域代理（关键：解决前端调用后端/predict接口的跨域问题）
  server: {
    proxy: {
      '/predict': {
        target: 'http://127.0.0.1:8000', // 后端服务地址
        changeOrigin: true,
        ws: true
      },
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    },
    port: 3000, // 前端端口，避免和后端8000冲突
    open: true // 启动自动打开页面
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  }
})