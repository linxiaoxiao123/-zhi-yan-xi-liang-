<template>
  <div class="settings-container">
    <!-- 头部导航 -->
    <AppHeader />

    <!-- 核心内容区 -->
    <main class="main-content">
      <div class="page-header">
        <h2 class="page-title">系统参数设置</h2>
        <p class="page-desc">配置系统运行的核心参数，包括数据汇总、文件清理等规则</p>
      </div>

      <!-- 数据汇总配置卡片 -->
      <div class="settings-card">
        <div class="settings-card-header">
          <h3 class="settings-title">⏰ 数据汇总配置</h3>
        </div>
        <div class="settings-form">
          <div class="form-item">
            <label class="form-label">每日汇总执行时间</label>
            <div class="time-input-group">
              <input 
                v-model.number="settings.dailySummaryHour" 
                type="number" 
                min="0" 
                max="23" 
                class="time-input hour-input"
                @input="validateHour"
              >
              <span class="time-sep">:</span>
              <input 
                v-model.number="settings.dailySummaryMinute" 
                type="number" 
                min="0" 
                max="59" 
                class="time-input minute-input"
                @input="validateMinute"
              >
              <span class="form-tip">（24小时制，例如 02:00 表示凌晨2点执行每日汇总）</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 数据清理配置卡片 -->
      <div class="settings-card card-orange">
        <div class="settings-card-header">
          <h3 class="settings-title">🗑️ 数据清理配置</h3>
        </div>
        <div class="settings-form">
          <div class="form-item">
            <label class="form-label">上传文件删除间隔（天）</label>
            <div class="input-group">
              <input 
                v-model.number="settings.uploadFileDeleteDays" 
                type="number" 
                min="1" 
                max="365" 
                class="number-input"
                @input="validateUploadDays"
              >
              <span class="unit">天</span>
              <span class="form-tip">（超过该天数的上传图片将被自动清理）</span>
            </div>
          </div>

          <div class="form-item">
            <label class="form-label">检测结果删除间隔（天）</label>
            <div class="input-group">
              <input 
                v-model.number="settings.detectionResultDeleteDays" 
                type="number" 
                min="1" 
                max="365" 
                class="number-input"
                @input="validateResultDays"
              >
              <span class="unit">天</span>
              <span class="form-tip">（超过该天数的检测结果将被自动清理）</span>
            </div>
          </div>

          <div class="form-item">
            <label class="form-label">汇总记录保留天数（天）</label>
            <div class="input-group">
              <input 
                v-model.number="settings.summaryRecordKeepDays" 
                type="number" 
                min="1" 
                max="3650" 
                class="number-input"
                @input="validateSummaryDays"
              >
              <span class="unit">天</span>
              <span class="form-tip">（超过该天数的历史汇总记录将被自动清理）</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 操作按钮区 -->
      <div class="action-buttons">
        <button 
          class="btn btn-outline reset-btn" 
          @click="resetSettings"
          :disabled="loading"
        >
          ↺ 恢复默认设置
        </button>
        <button 
          class="btn btn-primary save-btn" 
          @click="saveSettings"
          :disabled="loading"
        >
          {{ loading ? '🌀 保存中...' : '💾 保存设置' }}
        </button>
      </div>

      <!-- 全局提示弹窗 -->
      <div v-if="showToast" class="toast" :class="toastType">
        {{ toastMessage }}
      </div>
    </main>
  </div>
</template>

<script setup>
import axios from 'axios'
import { ref, onMounted } from 'vue'

// ==================== 全局配置 ====================
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// ==================== 响应式变量（全部5个配置） ====================
const settings = ref({
  dailySummaryHour: 2,
  dailySummaryMinute: 0,
  uploadFileDeleteDays: 90,
  detectionResultDeleteDays: 30,
  summaryRecordKeepDays: 90
})

// 默认配置
const DEFAULT_SETTINGS = {
  dailySummaryHour: 2,
  dailySummaryMinute: 0,
  uploadFileDeleteDays: 90,
  detectionResultDeleteDays: 30,
  summaryRecordKeepDays: 90
}

// 状态变量
const loading = ref(false)
const showToast = ref(false)
const toastType = ref('success')
const toastMessage = ref('')

// ==================== 完整输入验证方法 ====================
const validateHour = () => {
  let hour = parseInt(settings.value.dailySummaryHour)
  if (isNaN(hour) || hour < 0) settings.value.dailySummaryHour = 0
  if (hour > 23) settings.value.dailySummaryHour = 23
}

const validateMinute = () => {
  let minute = parseInt(settings.value.dailySummaryMinute)
  if (isNaN(minute) || minute < 0) settings.value.dailySummaryMinute = 0
  if (minute > 59) settings.value.dailySummaryMinute = 59
}

const validateUploadDays = () => {
  let days = parseInt(settings.value.uploadFileDeleteDays)
  if (isNaN(days) || days < 1) settings.value.uploadFileDeleteDays = 1
  if (days > 365) settings.value.uploadFileDeleteDays = 365
}

const validateResultDays = () => {
  let days = parseInt(settings.value.detectionResultDeleteDays)
  if (isNaN(days) || days < 1) settings.value.detectionResultDeleteDays = 1
  if (days > 365) settings.value.detectionResultDeleteDays = 365
}

const validateSummaryDays = () => {
  let days = parseInt(settings.value.summaryRecordKeepDays)
  if (isNaN(days) || days < 1) settings.value.summaryRecordKeepDays = 1
  if (days > 3650) settings.value.summaryRecordKeepDays = 3650
}

const validateAllSettings = () => {
  validateHour()
  validateMinute()
  validateUploadDays()
  validateResultDays()
  validateSummaryDays()
}

// ==================== 核心接口方法 ====================
const loadSettings = async () => {
  loading.value = true
  
  try {
    const res = await axios.get(`${API_BASE_URL}/api/configs`)
    settings.value.dailySummaryHour = res.data.daily_summary_hour ?? DEFAULT_SETTINGS.dailySummaryHour
    settings.value.dailySummaryMinute = res.data.daily_summary_minute ?? DEFAULT_SETTINGS.dailySummaryMinute
    settings.value.uploadFileDeleteDays = res.data.image_clean_days ?? DEFAULT_SETTINGS.uploadFileDeleteDays
    settings.value.detectionResultDeleteDays = res.data.records_clean_days ?? DEFAULT_SETTINGS.detectionResultDeleteDays
    settings.value.summaryRecordKeepDays = res.data.summary_keep_days ?? DEFAULT_SETTINGS.summaryRecordKeepDays
  } catch (err) {
    showToastMessage('加载设置失败，请检查后端服务是否启动', 'error')
    console.error('加载系统设置失败：', err)
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  validateAllSettings()
  
  loading.value = true
  try {
    await axios.post(`${API_BASE_URL}/api/configs`, null, {
      params: {
        daily_summary_hour: settings.value.dailySummaryHour,
        daily_summary_minute: settings.value.dailySummaryMinute,
        image_clean_days: settings.value.uploadFileDeleteDays,
        records_clean_days: settings.value.detectionResultDeleteDays,
        summary_keep_days: settings.value.summaryRecordKeepDays
      }
    })
    showToastMessage('设置保存成功！将在下次定时任务执行时生效', 'success')
  } catch (err) {
    let msg = '保存失败：'
    if (err.message.includes('Network Error')) {
      msg += '无法连接后端服务，请检查8000端口是否正常'
    } else {
      msg += err.response?.data?.msg || err.message
    }
    showToastMessage(msg, 'error')
    console.error('保存系统设置失败：', err)
  } finally {
    loading.value = false
  }
}

const resetSettings = async () => {
  if (!confirm('⚠️ 确定要将所有系统设置恢复为默认值吗？此操作不可撤销')) return
  
  loading.value = true
  try {
    settings.value = { ...DEFAULT_SETTINGS }
    await axios.post(`${API_BASE_URL}/api/configs`, null, {
      params: {
        daily_summary_hour: DEFAULT_SETTINGS.dailySummaryHour,
        daily_summary_minute: DEFAULT_SETTINGS.dailySummaryMinute,
        image_clean_days: DEFAULT_SETTINGS.uploadFileDeleteDays,
        records_clean_days: DEFAULT_SETTINGS.detectionResultDeleteDays,
        summary_keep_days: DEFAULT_SETTINGS.summaryRecordKeepDays
      }
    })
    showToastMessage('已成功恢复所有默认设置', 'success')
  } catch (err) {
    let msg = '恢复默认失败：'
    if (err.message.includes('Network Error')) {
      msg += '无法连接后端服务'
    } else {
      msg += err.response?.data?.msg || err.message
    }
    showToastMessage(msg, 'error')
    console.error('恢复默认设置失败：', err)
  } finally {
    loading.value = false
  }
}

const showToastMessage = (message, type) => {
  showToast.value = false
  setTimeout(() => {
    toastMessage.value = message
    toastType.value = type
    showToast.value = true
    
    setTimeout(() => {
      showToast.value = false
    }, 3000)
  }, 100)
}

// ==================== 页面初始化 ====================
onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
/* 基础样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.settings-container {
  min-height: 100vh;
  background-color: #f8fafc;
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
  color: #1e293b;
  display: flex;
  flex-direction: column;
}

/* 头部导航 */

.nav-link.active {
  background-color: #4f46e5;
  color: #ffffff;
  border-color: #4f46e5;
  box-shadow: 0 4px 8px rgba(79, 70, 229, 0.2);
}

/* 主内容区 */
.main-content {
  flex: 1;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 24px;
}

.page-header {
  padding: 30px 0 20px;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 32px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 8px;
}

.page-desc {
  font-size: 16px;
  color: #64748b;
  line-height: 1.5;
}

/* 设置卡片 */
.settings-card {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid #f1f5f9;
  margin-bottom: 24px;
  overflow: hidden;
  border-top: 4px solid #4f46e5;
}

.card-orange { border-top-color: #f59e0b; }

.settings-card-header {
  padding: 20px 24px;
  border-bottom: 1px solid #f1f5f9;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
}

.settings-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.settings-form {
  padding: 24px;
}

.form-item {
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 16px;
  font-weight: 500;
  color: #334155;
}

/* 时间输入组 */
.time-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.time-input {
  width: 80px;
  padding: 12px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 16px;
  text-align: center;
  transition: all 0.2s;
}

.time-input:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.hour-input {
  max-width: 80px;
}

.minute-input {
  max-width: 80px;
}

.time-sep {
  font-size: 18px;
  color: #64748b;
  font-weight: bold;
}

/* 数字输入组 */
.input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.number-input {
  width: 120px;
  padding: 12px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 16px;
  transition: all 0.2s;
}

.number-input:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.unit {
  font-size: 16px;
  color: #64748b;
  white-space: nowrap;
}

.form-tip {
  margin-left: 12px;
  font-size: 14px;
  color: #64748b;
  line-height: 1.4;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 16px;
  justify-content: flex-end;
  margin-top: 40px;
  margin-bottom: 40px;
}

.btn {
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s ease;
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-outline {
  background: #ffffff;
  color: #4f46e5;
  border: 2px solid #4f46e5;
}

.btn-outline:hover {
  background: #f0f4ff;
  color: #3730a3;
  border-color: #3730a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(79, 70, 229, 0.1);
}

.btn-primary {
  background: #4f46e5;
  color: #ffffff;
}

.btn-primary:hover {
  background: #3730a3;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(79, 70, 229, 0.2);
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

/* 提示弹窗 */
.toast {
  position: fixed;
  top: 80px;
  right: 24px;
  padding: 12px 24px;
  border-radius: 8px;
  color: #ffffff;
  font-size: 16px;
  z-index: 9999;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  animation: slideIn 0.3s ease, fadeOut 0.3s ease 2.7s;
}

.toast.success {
  background-color: #10b981;
}

.toast.error {
  background-color: #ef4444;
}

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

@keyframes fadeOut {
  from { opacity: 1; }
  to { opacity: 0; }
}

/* 响应式适配 */
@media (max-width: 1200px) {
  
  .main-content {
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  
  
  
  
  .page-title {
    font-size: 22px;
  }
  .action-buttons {
    flex-direction: column;
    gap: 12px;
  }
  .btn {
    width: 100%;
    justify-content: center;
  }
}

@media (max-width: 480px) {
  .main-content {
    padding: 0 16px;
  }
  .settings-form {
    padding: 16px;
  }
  .form-item {
    margin-bottom: 20px;
  }
  .time-input-group, .input-group {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .form-tip {
    margin-left: 0;
    margin-top: 4px;
  }
  .toast {
    left: 16px;
    right: 16px;
    text-align: center;
  }
}
</style>