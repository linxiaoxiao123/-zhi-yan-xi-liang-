<template>
  <div class="summary-container">
    <AppHeader />

    <main class="main-content">
      <div class="page-header">
        <h2 class="page-title">数据汇总分析</h2>
        <p class="page-desc">多维度分析餐食浪费情况，直观展示统计结果</p>
      </div>

      <div class="filter-card">
        <div class="filter-header">
          <h3 class="filter-title">数据筛选</h3>
        </div>
        <div class="filter-form">
          <div class="time-filter">
            <div class="filter-item">
              <label class="filter-label">统计维度</label>
              <select v-model="timeDimension" class="filter-select">
                <option value="day">按日统计</option>
                <option value="week">按周统计</option>
                <option value="month">按月统计</option>
              </select>
            </div>

            <div class="filter-item date-filter-item">
              <label class="filter-label">时间范围</label>
              <div class="date-group">
                <input v-model="startDate" type="date" class="date-input" :disabled="timeDimension !== 'day'" />
                <span class="date-sep">至</span>
                <input v-model="endDate" type="date" class="date-input" :disabled="timeDimension !== 'day'" />
                <button @click="fetchSummaryData" class="btn btn-primary filter-btn">📊 刷新数据</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="overview-card">
        <div class="overview-item">
          <span class="overview-label">总检测次数</span>
          <span class="overview-value">{{ overviewData.totalCount || 0 }}</span>
          <span class="overview-desc">次</span>
        </div>
        <div class="overview-item">
          <span class="overview-label">平均浪费率</span>
          <span class="overview-value">{{ overviewData.avgWasteRate || 0 }}</span>
          <span class="overview-desc">%</span>
        </div>
        <div class="overview-item">
          <span class="overview-label">高浪费记录</span>
          <span class="overview-value">{{ overviewData.highWasteCount || 0 }}</span>
          <span class="overview-desc">条</span>
        </div>
        <div class="overview-item">
          <span class="overview-label">检测成功率</span>
          <span class="overview-value">{{ overviewData.successRate || 0 }}</span>
          <span class="overview-desc">%</span>
        </div>
      </div>

      <div class="chart-container">
        <div v-if="loading" class="loading-container">
          <div class="loading-spinner">🌀</div>
          <span class="loading-text">正在加载图表数据...</span>
        </div>

        <div v-else class="chart-grid">
          <div class="chart-card">
            <div class="chart-card-header">
              <h3 class="chart-title">{{ timeDimensionMap[timeDimension] }}浪费率趋势</h3>
            </div>
            <div class="chart-content">
              <canvas id="trendChart" style="width: 100%; height: 300px"></canvas>
            </div>
          </div>

          <div class="chart-card">
            <div class="chart-card-header">
              <h3 class="chart-title">菜品浪费占比</h3>
            </div>
            <div class="chart-content">
              <canvas id="foodChart" style="width: 100%; height: 300px"></canvas>
            </div>
          </div>

          <div class="chart-card full-width">
            <div class="chart-card-header">
              <h3 class="chart-title">检测方式统计</h3>
            </div>
            <div class="chart-content">
              <canvas id="uploadChart" style="width: 100%; height: 300px"></canvas>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted, nextTick } from 'vue'
import * as ChartJS from 'chart.js'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const { Chart, registerables } = ChartJS
Chart.register(...registerables)

const timeDimension = ref('day')
const startDate = ref('')
const endDate = ref('')
const loading = ref(false)

const timeDimensionMap = {
  day: '每日',
  week: '每周',
  month: '每月',
}

const overviewData = ref({})
let trendChart = null
let foodChart = null
let uploadChart = null

// ✅ 优化：仅错误时弹窗，成功不弹
const showToast = (title) => {
  if (title.includes('失败')) {
    alert(title)
  }
}

const initDateRange = () => {
  const now = new Date()
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
  endDate.value = now.toISOString().split('T')[0]
  startDate.value = thirtyDaysAgo.toISOString().split('T')[0]
}

const fetchSummaryData = async () => {
  loading.value = true
  try {
    const isDay = timeDimension.value === 'day'
    const params = {
      time_dim: timeDimension.value,
      ...(isDay && {
        start_time: `${startDate.value} 00:00:00`,
        end_time: `${endDate.value} 23:59:59`
      })
    }

    const [overviewRes, trendRes, foodRes, uploadRes] = await Promise.all([
      axios.get(`${API_BASE_URL}/api/overview`, { params: isDay ? { start_time: params.start_time, end_time: params.end_time } : {} }),
      axios.get(`${API_BASE_URL}/api/statistics`, { params: { ...params, type: 'trend' } }),
      axios.get(`${API_BASE_URL}/api/statistics`, { params: { ...params, type: 'food' } }),
      axios.get(`${API_BASE_URL}/api/statistics`, { params: { ...params, type: 'upload' } })
    ])

    overviewData.value = overviewRes.data

    if (trendChart) trendChart.destroy()
    if (foodChart) foodChart.destroy()
    if (uploadChart) uploadChart.destroy()

    loading.value = false
    await nextTick()

    renderTrendChart(trendRes.data)
    renderFoodChart(foodRes.data)
    renderUploadChart(uploadRes.data)

    // ✅ 核心：删除了成功弹窗！
  } catch (err) {
    console.error('获取数据失败：', err)
    showToast('数据加载失败，请检查后端服务')
    loading.value = false
  }
}

const renderTrendChart = (data) => {
  const canvas = document.getElementById('trendChart')
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.labels.length ? data.labels : ['暂无数据'],
      datasets: [{
        label: '浪费率（%）',
        data: data.wasteRates.length ? data.wasteRates : [0],
        borderColor: '#4f46e5',
        backgroundColor: 'rgba(79,70,229,0.1)',
        tension: 0.4,
        fill: true,
        pointRadius: 4,
        pointHoverRadius: 6
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          backgroundColor: 'rgba(255,255,255,0.95)',
          titleColor: '#1e293b',
          bodyColor: '#1e293b',
          borderColor: '#e2e8f0',
          borderWidth: 1,
          padding: 12
        },
        legend: { labels: { font: { size: 14, family: 'Microsoft YaHei' } } }
      },
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } },
        x: { grid: { display: false } }
      }
    }
  })
}

const renderFoodChart = (data) => {
  const canvas = document.getElementById('foodChart')
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  
  const labels = data.labels.length ? data.labels : ['暂无数据']
  const values = data.values.length ? data.values : [100]
  
  foodChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6'],
        borderWidth: 2,
        borderColor: '#ffffff'
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed}%` } },
        legend: { position: 'right', labels: { font: { size: 14, family: 'Microsoft YaHei' } } }
      },
      cutout: '60%'
    }
  })
}

const renderUploadChart = (data) => {
  const canvas = document.getElementById('uploadChart')
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  
  const labels = data.labels.length ? data.labels : ['暂无数据']
  const counts = data.counts.length ? data.counts : [0]
  
  uploadChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: '检测次数',
        data: counts,
        backgroundColor: ['rgba(79, 70, 229, 0.8)', 'rgba(16, 185, 129, 0.8)', 'rgba(245, 158, 11, 0.8)'],
        borderColor: ['#4f46e5', '#10b981', '#f59e0b'],
        borderWidth: 2,
        borderRadius: 6
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true }, x: { grid: { display: false } } }
    }
  })
}

onMounted(() => {
  initDateRange()
  fetchSummaryData()
})

onUnmounted(() => {
  if (trendChart) trendChart.destroy()
  if (foodChart) foodChart.destroy()
  if (uploadChart) uploadChart.destroy()
})

watch(timeDimension, () => {
  if (timeDimension.value !== 'day') {
    startDate.value = ''
    endDate.value = ''
  } else {
    initDateRange()
  }
  fetchSummaryData()
})
</script>

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.summary-container {
  min-height: 100vh;
  background: #f8fafc;
  font-family: "Microsoft YaHei", sans-serif;
  color: #1e293b;
}

.nav-link.active {
  background: #4f46e5;
  color: #fff;
}

.main-content {
  max-width: 1500px;
  margin: 0 auto;
  padding: 0 24px;
}

.page-header {
  padding: 40px 0 24px;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 24px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
}

.page-desc {
  color: #64748b;
  font-size: 16px;
}

.filter-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.filter-header {
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.filter-title {
  font-size: 18px;
  font-weight: 600;
}

.time-filter {
  display: flex;
  align-items: center;
  gap: 30px;
  flex-wrap: wrap;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-width: 200px;
}

.filter-label {
  font-size: 14px;
  color: #334155;
  font-weight: 500;
}

.filter-select,
.date-input {
  padding: 12px 16px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 14px;
  height: 48px;
}

.date-input:disabled {
  background: #f1f5f9;
  cursor: not-allowed;
}

.date-group {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 48px;
}

.date-sep {
  color: #64748b;
}

.filter-btn {
  padding: 0 20px;
  height: 48px;
  border-radius: 8px;
  background: #4f46e5;
  color: #fff;
  border: none;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.filter-btn:hover {
  background: #3730a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(79, 70, 229, 0.2);
}

.overview-card {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.overview-item {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  transition: all 0.2s;
}

.overview-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.06);
}

.overview-label {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 8px;
}

.overview-value {
  font-size: 32px;
  font-weight: 700;
  color: #4f46e5;
  line-height: 1.2;
}

.overview-desc {
  font-size: 14px;
  color: #64748b;
  margin-top: 4px;
}

.chart-container {
  margin-bottom: 40px;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 16px;
  color: #64748b;
}

.loading-spinner {
  font-size: 32px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.chart-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid #f1f5f9;
  padding: 0;
  display: flex;
  flex-direction: column;
  height: 420px;
  overflow: hidden;
  transition: all 0.2s;
}

.chart-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border-color: #e2e8f0;
}

.chart-card-header {
  padding: 20px 24px;
  border-bottom: 1px solid #f1f5f9;
}

.chart-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.chart-content {
  flex: 1;
  position: relative;
  padding: 20px 24px;
  min-height: 350px;
}

.full-width {
  grid-column: 1 / -1;
}

@media (max-width: 1200px) {
  .chart-grid {
    grid-template-columns: 1fr;
    gap: 20px;
  }
  .chart-card {
    height: 380px;
  }
  
  .overview-card {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  
  .time-filter {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
  .filter-item, .date-filter-item {
    flex: 1;
    min-width: unset;
  }
  .overview-card {
    grid-template-columns: 1fr;
  }
  .chart-card {
    height: 340px;
  }
  .page-title {
    font-size: 24px;
  }
}
</style>