import { createApp } from 'vue'
import router from './router' // 引入路由
import App from './App.vue'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import axios from 'axios'

// 全局设置接口鉴权 token（与后端 API_TOKEN 保持一致，可用 .env 的 VITE_API_TOKEN 覆盖）
const API_TOKEN = import.meta.env.VITE_API_TOKEN || 'zhongyan-xiliang-2026'
axios.defaults.headers.common['Authorization'] = `Bearer ${API_TOKEN}`

// 全局注册公共组件 + 挂载路由
const app = createApp(App)
app.component('AppHeader', AppHeader)
app.component('AppFooter', AppFooter)
app.use(router) // 必须加这行，否则router-link无效
app.mount('#app')