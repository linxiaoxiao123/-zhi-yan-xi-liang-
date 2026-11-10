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
  server: {
    port: 3000, // 前端端口，避免和后端8000冲突
    open: true // 启动自动打开页面
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  }
})