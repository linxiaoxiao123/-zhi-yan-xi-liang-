import { createRouter, createWebHistory } from 'vue-router'
// 确认文件路径和名称与实际一致！
import Home from '../views/Home.vue'
import DetectionRecord from '../views/DetectionRecord.vue'
import DataSummary from '../views/DataSummary.vue'
import SystemSettings from '@/views/SystemSettings.vue'
import JudgeScoring from '@/views/JudgeScoring.vue'

const routes = [
  {
    path: '/',          // 首页路由
    name: 'Home',
    component: Home
  },
  {
    path: '/detection-record',  // 检测记录路由
    name: 'DetectionRecord',
    component: DetectionRecord
  },
  {
    path: '/data-summary',      // 数据汇总路由
    name: 'DataSummary',
    component: DataSummary
  },
  {
    path: '/judge-scoring',
    name: 'JudgeScoring',
    component: JudgeScoring
  },
  {
      path: '/system-settings',
      name: 'SystemSettings',
      component: SystemSettings
  }
]

const router = createRouter({
  history: createWebHistory(),  // 确保使用HTML5 history模式
  routes
})

export default router