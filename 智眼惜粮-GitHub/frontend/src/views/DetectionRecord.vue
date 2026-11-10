<template>
  <div class="record-container">
    <AppHeader />

    <main class="main-content">
      <div class="page-header">
        <h2 class="page-title">检测记录管理</h2>
        <p class="page-desc">筛选并查看所有餐食浪费检测历史记录</p>
      </div>

      <div class="filter-card">
        <div class="filter-header">
          <h3 class="filter-title">筛选条件</h3>
        </div>
        <div class="filter-form">
          <div class="filter-grid">
            <div class="filter-item">
              <label class="filter-label">菜品名称</label>
              <input 
                v-model="filterFood" 
                type="text" 
                placeholder="请输入菜品关键词" 
                class="filter-input"
              >
            </div>
            <div class="filter-item">
              <label class="filter-label">浪费率区间</label>
              <div class="range-group">
                <input 
                  v-model.number="filterWasteMin" 
                  type="number" 
                  min="0" 
                  max="100" 
                  placeholder="0" 
                  class="range-input"
                >
                <span class="range-sep">-</span>
                <input 
                  v-model.number="filterWasteMax" 
                  type="number" 
                  min="0" 
                  max="100" 
                  placeholder="100" 
                  class="range-input"
                >
                <span class="range-unit">%</span>
              </div>
            </div>
            <div class="filter-item">
              <label class="filter-label">检测类型</label>
              <select v-model="filterType" class="filter-select">
                <option value="">全部类型</option>
                <option value="single">单张上传</option>
                <option value="batch">批量上传</option>
                <option value="camera">摄像头抓拍</option>
              </select>
            </div>
            <div class="filter-item">
              <label class="filter-label">检测时间</label>
              <div class="date-group">
                <input v-model="filterStartDate" type="date" class="date-input">
                <span class="date-sep">至</span>
                <input v-model="filterEndDate" type="date" class="date-input">
              </div>
            </div>
          </div>
          <div class="filter-actions">
            <button @click="searchRecords" class="btn btn-primary filter-btn">🔍 筛选</button>
            <button @click="resetFilter" class="btn btn-outline filter-btn">🔄 重置</button>
          </div>
        </div>
      </div>

      <div v-if="activeFilters.length" class="active-filters">
        <span class="filters-label">已选筛选：</span>
        <span v-for="f in activeFilters" :key="f.key" class="filter-chip" @click="removeFilter(f.key)">
          {{ f.label }} <span class="chip-close">✕</span>
        </span>
      </div>

      <div class="record-card">
        <div v-if="loading" class="loading-container">
          <span class="loading-icon">🌀</span>
          <span class="loading-text">正在加载检测记录...</span>
        </div>
        
        <div v-else-if="recordList && recordList.length === 0" class="empty-container">
          <span class="empty-icon">📭</span>
          <span class="empty-text">暂无符合条件的检测记录</span>
        </div>
        
        <div v-else class="table-container">
          <table class="record-table">
            <thead>
              <tr class="table-header">
                <th width="60">序号</th>
                <th width="180">检测时间</th>
                <th width="100">检测类型</th>
                <th width="200">检测文件</th>
                <th width="180">检测菜品</th>
                <th width="100">浪费率</th>
                <th width="100">检测状态</th>
              </tr>
            </thead>
            <tbody>
              <tr 
                v-for="(item, index) in recordList" 
                :key="item.id" 
                class="table-row"
                :class="{ 'row-hover': hoverIndex === index }"
                @mouseenter="hoverIndex = index"
                @mouseleave="hoverIndex = -1"
              >
                <td>{{ index + 1 }}</td>
                <td>{{ item.create_time || item.update_time }}</td>
                <td>
                  <span class="type-tag" :class="item.record_type">
                    {{ item.record_type === 'single' ? '单张上传' : item.record_type === 'batch' ? '批量上传' : '摄像头抓拍' }}
                  </span>
                </td>
                <td class="file-name">{{ item.file_name }}</td>
                <td>{{ item.items.map(i => i.food_name).join('、') }}</td>
                <td>
                  <span class="waste-tag" :class="getWasteClass(item.wastage_rate)">
                    {{ item.wastage_rate }}%
                  </span>
                </td>
                <td>
                  <span class="status-tag success" >
					  成功
                  </span>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="pagination-container">
            <button 
              class="page-btn" 
              @click="changePage(currentPage - 1)"
              :disabled="currentPage === 1 || loading"
            >
              ← 上一页
            </button>
            <span class="page-info">第 {{ currentPage }} 页 / 共 {{ totalPages }} 页</span>
            <button 
              class="page-btn" 
              @click="changePage(currentPage + 1)"
              :disabled="currentPage === totalPages || loading"
            >
              下一页 →
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// 全部筛选条件
const filterFood = ref('')
const filterWasteMin = ref('')
const filterWasteMax = ref('')
const filterType = ref('')
const filterStartDate = ref('')
const filterEndDate = ref('')

// 分页与数据
const currentPage = ref(1)
const pageSize = ref(10)
const totalPages = ref(1)
const loading = ref(false)
const hoverIndex = ref(-1)
const recordList = ref([])

// 核心方法：传递全部筛选参数
const fetchRecords = async () => {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value
    }

    if (filterType.value) params.record_type = filterType.value
    if (filterFood.value.trim()) params.food_name = filterFood.value.trim()
    
    if (filterWasteMin.value !== '' && filterWasteMin.value !== null) {
      params.waste_min = Number(filterWasteMin.value)
    }
    if (filterWasteMax.value !== '' && filterWasteMax.value !== null) {
      params.waste_max = Number(filterWasteMax.value)
    }
    
    if (filterStartDate.value) params.start_time = filterStartDate.value
    if (filterEndDate.value) {
      const endDate = new Date(filterEndDate.value)
      endDate.setDate(endDate.getDate() + 1)
      params.end_time = endDate.toISOString().split('T')[0]
    }

    const res = await axios.get(`${API_BASE_URL}/batch_results`, { params })
    
    recordList.value = res.data.data.records || []
    totalPages.value = res.data.data.pagination?.total_pages || 1
  } catch (err) {
    console.error('获取检测记录失败：', err)
    recordList.value = []
    totalPages.value = 1
  } finally {
    loading.value = false
  }
}

// 浪费率区间合法性校验
const searchRecords = () => {
  if (
    filterWasteMin.value !== '' && 
    filterWasteMax.value !== '' && 
    Number(filterWasteMin.value) > Number(filterWasteMax.value)
  ) {
    [filterWasteMin.value, filterWasteMax.value] = [filterWasteMax.value, filterWasteMin.value]
  }
  
  currentPage.value = 1
  fetchRecords()
}

const resetFilter = () => {
  filterFood.value = ''
  filterWasteMin.value = ''
  filterWasteMax.value = ''
  filterType.value = ''
  
  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  filterEndDate.value = now.toISOString().split('T')[0]
  filterStartDate.value = sevenDaysAgo.toISOString().split('T')[0]
  
  currentPage.value = 1
  fetchRecords()
}

// 已选筛选条件（chip 标签）
const activeFilters = computed(() => {
  const list = []
  if (filterFood.value.trim()) list.push({ key: 'food', label: `菜品「${filterFood.value.trim()}」` })
  if (filterWasteMin.value !== '' || filterWasteMax.value !== '') {
    const min = filterWasteMin.value !== '' ? filterWasteMin.value : 0
    const max = filterWasteMax.value !== '' ? filterWasteMax.value : 100
    list.push({ key: 'waste', label: `浪费率 ${min}%~${max}%` })
  }
  if (filterType.value) {
    const typeMap = { single: '单张上传', batch: '批量上传', camera: '摄像头抓拍' }
    list.push({ key: 'type', label: `类型：${typeMap[filterType.value] || filterType.value}` })
  }
  return list
})

const removeFilter = (key) => {
  if (key === 'food') filterFood.value = ''
  else if (key === 'waste') { filterWasteMin.value = ''; filterWasteMax.value = '' }
  else if (key === 'type') filterType.value = ''
  searchRecords()
}

const changePage = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchRecords()
  }
}

const getWasteClass = (rate) => rate < 20 ? 'low' : rate < 50 ? 'medium' : 'high'

onMounted(() => {
  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  filterEndDate.value = now.toISOString().split('T')[0]
  filterStartDate.value = sevenDaysAgo.toISOString().split('T')[0]
  fetchRecords()
})
</script>

<style scoped>
.record-container {
  min-height: 100vh;
  background-color: #f8faff;
  display: flex;
  flex-direction: column;
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
}

.nav-link.active {
  background-color: #6366f1;
  color: #fff;
  border-color: #6366f1;
}

.page-header {
  padding: 30px 20px 20px;
  margin: 0 auto;
  max-width: 1400px;
  width: 100%;
}

.page-title {
  font-size: 24px;
  color: #1e293b;
  margin: 0 0 8px 0;
  font-weight: 600;
}

.page-desc {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

.filter-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  padding: 24px;
  margin: 0 auto 20px;
  max-width: 1400px;
  width: calc(100% - 40px);
}

.filter-header {
  margin-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 8px;
}

.filter-title {
  font-size: 16px;
  color: #1e293b;
  font-weight: 600;
  margin: 0;
}

.filter-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  color: #334155;
  font-weight: 500;
  line-height: 1.2;
}

.filter-input, .filter-select, .range-input, .date-input {
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
  height: 40px;
  box-sizing: border-box;
  transition: all 0.2s;
}

.filter-input:focus, .filter-select:focus, .range-input:focus, .date-input:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
}

.range-group, .date-group {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
}

.range-sep, .date-sep {
  color: #94a3b8;
  font-size: 14px;
  white-space: nowrap;
}

.range-unit {
  color: #94a3b8;
  font-size: 14px;
  margin-left: 4px;
  white-space: nowrap;
}

.range-input {
  flex: 1;
  min-width: 60px;
  text-align: center;
}

.date-input {
  min-width: 120px;
}

.filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 8px;
}

.filter-btn {
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 100px;
}

.btn {
  border: none;
  transition: all 0.2s;
  font-weight: 500;
}

.btn-primary {
  background: #6366f1;
  color: #fff;
}

.btn-primary:hover {
  background: #4f46e5;
}

.btn-outline {
  background: #fff;
  color: #6366f1;
  border: 1px solid #6366f1;
}

.btn-outline:hover {
  background: #f0f4ff;
}

/* 已选筛选条件 chip */
.active-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  max-width: 1400px;
  margin-left: auto;
  margin-right: auto;
}
.filters-label {
  font-size: 14px;
  color: #64748b;
  font-weight: 500;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #eef2ff;
  color: #4f46e5;
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-chip:hover {
  background: #e0e7ff;
}
.chip-close {
  font-size: 12px;
  color: #818cf8;
}

.record-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  padding: 20px;
  margin: 0 auto 30px;
  max-width: 1400px;
  width: calc(100% - 40px);
}

.loading-container, .empty-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 12px;
  color: #64748b;
}

.loading-icon {
  font-size: 24px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-text, .empty-text {
  font-size: 16px;
}

.empty-icon {
  font-size: 32px;
}

.table-container {
  overflow-x: auto;
}

.record-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 800px;
  border-radius: 8px;
  overflow: hidden;
}

.table-header {
  background: #f8fafc;
}

.table-header th {
  padding: 14px 12px;
  text-align: left;
  color: #1e293b;
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid #e2e8f0;
}

.table-row {
  border-bottom: 1px solid #f1f5f9;
}

.table-row td {
  padding: 14px 12px;
  color: #334155;
  font-size: 14px;
}

.row-hover {
  background: #f8fafc;
}

.type-tag {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.type-tag.single { background: #dcfce7; color: #22c55e; }
.type-tag.batch { background: #fef3c7; color: #f59e0b; }
.type-tag.camera { background: #dbeafe; color: #3b82f6; }

.waste-tag {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

.waste-tag.low { background: #10b981; }
.waste-tag.medium { background: #f59e0b; }
.waste-tag.high { background: #ef4444; }

.status-tag {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-tag.success { background: #dcfce7; color: #16a34a; }
.status-tag.failed { background: #fee2e2; color: #dc2626; }

.file-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pagination-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #f1f5f9;
}

.page-btn {
  padding: 8px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  color: #6366f1;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: #6366f1;
  color: #fff;
  border-color: #6366f1;
}

.page-btn:disabled {
  color: #94a3b8;
  cursor: not-allowed;
  background: #f8fafc;
}

.page-info {
  font-size: 14px;
  color: #64748b;
}

@media (max-width: 1200px) {
  .filter-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }
  .filter-actions {
    justify-content: flex-start;
  }
  
  
  
}
</style>