<template>
  <div class="app-container">
    <AppHeader />

    <main class="main-content">
      <section class="hero-section">
        <div class="hero-left">
          <h1 class="hero-title">智能识别 · 高效管理</h1>
          <p class="hero-subtitle">智眼惜粮——食堂餐食浪费智能监测与分析系统</p>
          <p class="hero-desc">
            通过AI视觉识别技术，自动检测餐盘中剩余菜品，实现食堂精细化管理与节约型校园建设。
          </p>
          <div class="hero-buttons">
            <button class="btn btn-primary" @click="openCameraModal">📷 摄像头抓拍</button>
            <button class="btn btn-outline" @click="switchToSingleMode">🖼️ 单张模型</button>
            <button class="btn btn-outline" @click="switchToBatchMode">📚 批量模型</button>
          </div>
        </div>
      </section>

      <section class="upload-section">
        <div class="upload-card" @dragover.prevent @drop.prevent="handleDrop">
          <div class="upload-icon">☁️</div>
          <h3 class="upload-title">
            {{ isBatchMode ? '批量模型检测' : '单张模型检测' }}
          </h3>
          <p class="upload-desc">
            {{ isBatchMode ? '支持PNG、JPG、BMP、WEBP格式，总大小不超过100MB' : '支持PNG、JPG、BMP、WEBP格式，单张不超过15MB，单次仅上传1张' }}
          </p>
          
          <input 
            type="file" 
            ref="singleFileInput" 
            accept="image/*" 
            style="display: none" 
            @change="handleSingleFileSelect"
          />
          <input 
            type="file" 
            ref="batchFileInput" 
            accept="image/*" 
            multiple 
            style="display: none" 
            @change="handleBatchFileSelect"
          />
          
          <div class="button-group">
            <button 
              class="btn btn-outline select-btn" 
              @click="triggerFileSelect"
            >
              📁 选择图片
            </button>
            <button 
              class="btn btn-primary detect-btn" 
              @click="isBatchMode ? submitBatchToBackend() : submitSingleToBackend()" 
              :disabled="loading || (isBatchMode ? !selectedBatchFiles.length : !selectedSingleFile)"
            >
              {{ loading ? '⏳ 检测中...' : '🔍 开始检测' }}
            </button>
          </div>
          
          <div v-if="selectedSingleFile && !isBatchMode" class="file-preview">
            <img v-if="singlePreviewUrl" :src="singlePreviewUrl" class="preview-thumb" alt="预览" />
            <span class="file-tip">已选择：{{ selectedSingleFile.name }}</span>
          </div>
          <div v-if="selectedBatchFiles.length && isBatchMode" class="file-preview">
            <div class="preview-thumbs">
              <img v-for="(file, index) in selectedBatchFiles.slice(0, 6)" :key="index" :src="batchPreviewUrls[index]" class="preview-thumb" alt="预览" />
            </div>
            <span class="file-tip">已选择 {{ selectedBatchFiles.length }} 个文件{{ selectedBatchFiles.length > 6 ? '（仅预览前 6 张）' : '' }}</span>
          </div>

          <div v-if="singleResult && !isBatchMode" class="result-box single-result">
            <h4>✅ 检测结果：{{ singleResult.filename }}</h4>
            <div class="result-images">
              <div class="img-item">
                <img :src="singleResult.original_image_url" alt="原图" class="result-img" />
                <p>原图</p>
              </div>
              <div class="img-item">
                <img :src="singleResult.result_image_url" alt="检测图" class="result-img" />
                <p>检测图</p>
              </div>
              <div class="img-item">
                <img :src="singleResult.mask_image_url" alt="掩码图" class="result-img" />
                <p>掩码图</p>
              </div>
            </div>
            <div class="result-data">
              <p><strong>检测菜品：</strong>{{ getUniqueFoods(singleResult.detections).join('、') || '未检测到菜品' }}</p>
              <p><strong>菜品数量：</strong>{{ getUniqueFoods(singleResult.detections).length }}</p>
              <p :class="['waste-ratio', wasteRateClass(singleResult.wastage_rate)]"><strong>浪费率：</strong>{{ singleResult.wastage_rate }}%</p>
              <p><strong>状态：</strong>{{ singleResult.status }}</p>
              <p v-if="singleResult.waste_cause"><strong>弃因分析：</strong>
                <span :class="causeClass(singleResult.waste_cause)">{{ singleResult.waste_cause }}</span>
                <span v-if="singleResult.waste_cause_confidence" class="cause-conf">({{ (singleResult.waste_cause_confidence * 100).toFixed(1) }}%)</span>
              </p>
            </div>
          </div>

          <div v-if="batchResult && isBatchMode" class="batch-result-container">
            <div class="batch-summary single-result">
              <h4>✅ 批量检测完成</h4>
              <p>总文件数：{{ batchResult.total_count }} | 成功：{{ batchResult.success_count }} | 失败：{{ batchResult.fail_count }}</p>
            </div>
            
            <div v-if="batchPageResults.data?.records?.length" class="batch-results">
              <div class="result-box single-result" v-for="(item, index) in batchPageResults.data.records" :key="index">
                <div v-if="!item.error">
                  <h4>✅ 检测结果：{{ item.file_name }}</h4>
                  <div class="result-images">
                    <div class="img-item">
                      <img :src="item.original_image_url" alt="原图" class="result-img" />
                      <p>原图</p>
                    </div>
                    <div class="img-item">
                      <img :src="item.result_image_url" alt="检测图" class="result-img" />
                      <p>检测图</p>
                    </div>
                    <div class="img-item">
                      <img :src="item.mask_image_url" alt="掩码图" class="result-img" />
                      <p>掩码图</p>
                    </div>
                  </div>
                  <div class="result-data">
                    <p><strong>检测菜品：</strong>{{ getUniqueFoods(item.items || item.detections).join('、') || '未检测到菜品' }}</p>
                    <p><strong>菜品数量：</strong>{{ getUniqueFoods(item.items || item.detections).length }}</p>
                    <p :class="['waste-ratio', wasteRateClass(item.wastage_rate)]"><strong>浪费率：</strong>{{ item.wastage_rate }}%</p>
                    <p><strong>状态：</strong>{{ item.status }}</p>
                    <p v-if="item.waste_cause"><strong>弃因分析：</strong>
                      <span :class="causeClass(item.waste_cause)">{{ item.waste_cause }}</span>
                      <span v-if="item.waste_cause_confidence" class="cause-conf">({{ (item.waste_cause_confidence * 100).toFixed(1) }}%)</span>
                    </p>
                  </div>
                </div>
                <div v-else class="fail-card">
                  <h4>❌ 检测失败：{{ item.file_name }}</h4>
                  <p class="error-text">❌ 检测失败：{{ item.error }}</p>
                </div>
              </div>
            </div>
            
            <div v-if="batchPageResults.data?.pagination" class="pagination">
              <button 
                class="btn btn-outline page-btn" 
                @click="changeBatchPage(batchPageResults.data.pagination.page - 1)"
                :disabled="!batchPageResults.data.pagination.has_prev || loading"
              >
                ← 上一页
              </button>
              
              <div class="page-select-container">
                <select 
                  class="page-select"
                  v-model="targetPage"
                  @change="jumpToTargetPage"
                  :disabled="loading"
                >
                  <option 
                    v-for="page in batchPageResults.data.pagination.total_pages" 
                    :key="page"
                    :value="page"
                  >
                    第 {{ page }} 页
                  </option>
                </select>
              </div>
              
              <span class="page-info">
                / 共 {{ batchPageResults.data.pagination.total_pages }} 页
              </span>
              
              <button 
                class="btn btn-outline page-btn" 
                @click="changeBatchPage(batchPageResults.data.pagination.page + 1)"
                :disabled="!batchPageResults.data.pagination.has_next || loading"
              >
                下一页 →
              </button>
            </div>
          </div>

          <div v-if="loading" class="loading-tip">
            🌀 {{ isBatchMode ? '批量检测中' : '检测中' }}，请稍候...
          </div>

          <div v-if="errorMsg" class="error-tip">
            ❌ {{ errorMsg }}
          </div>
        </div>
      </section>
    </main>

    <!-- 摄像头弹窗 -->
    <div v-if="cameraModalVisible" class="modal-overlay" @click="closeCameraModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>📹 摄像头传送带抓拍模式</h3>
          <button class="modal-close" @click="closeCameraModal">×</button>
        </div>
        
        <div class="modal-body">
          <div class="camera-control-panel">
            <button 
              class="btn btn-primary" 
              @click="toggleCamera"
              :disabled="cameraLoading"
            >
              {{ cameraActive ? '🔴 关闭摄像头' : '🟢 开启摄像头' }}
            </button>
            
            <div class="auto-capture-controls" v-if="cameraActive">
              <button 
                class="btn btn-outline" 
                @click="manualCapture"
                :disabled="autoCaptureActive || cameraLoading"
              >
                📷 手动抓拍
              </button>
              
              <button 
                class="btn" 
                :class="autoCaptureActive ? 'btn-outline' : 'btn-primary'"
                @click="toggleAutoCapture"
                :disabled="cameraLoading"
              >
                {{ autoCaptureActive ? '⏹️ 停止传送带模式' : '▶️ 启动传送带模式' }}
              </button>
              
              <div class="interval-setting">
                <label>抓拍间隔：</label>
                <input 
                  type="number" 
                  v-model.number="captureInterval" 
                  min="1" 
                  max="30" 
                  class="interval-input"
                  :disabled="autoCaptureActive || cameraLoading"
                />
                <span>秒</span>
              </div>
            </div>
          </div>
          
          <div class="camera-preview-container" :class="{ 'hidden': !cameraActive }">
            <video 
              ref="videoRef" 
              class="camera-preview" 
              autoplay 
              playsinline 
              muted
            ></video>
            
            <div class="capture-preview-box" v-if="captureImage">
              <h4>最新抓拍预览</h4>
              <img :src="captureImage" alt="抓拍预览" class="capture-preview-img" />
            </div>
          </div>
          
          <div class="camera-tip" v-if="!cameraActive && !cameraErrorMsg">
            请点击"开启摄像头"，授权后使用手动/传送带自动抓拍+检测功能
          </div>
          
          <div v-if="cameraLoading" class="loading-tip">
            🌀 {{ autoCaptureActive ? '自动抓拍检测中' : '处理中' }}，请稍候...
          </div>
          <div v-if="cameraErrorMsg" class="error-tip">
            ❌ {{ cameraErrorMsg }}
          </div>
          
          <div v-if="cameraDetectResult" class="camera-result-section single-result">
            <h4>✅ 抓拍检测结果</h4>
            <div class="result-images">
              <div class="img-item">
                <img :src="cameraDetectResult.original_image_url || captureImage" alt="抓拍原图" class="result-img" />
                <p>抓拍原图</p>
              </div>
              <div class="img-item">
                <img :src="cameraDetectResult.result_image_url" alt="检测图" class="result-img" />
                <p>检测图</p>
              </div>
              <div class="img-item">
                <img :src="cameraDetectResult.mask_image_url" alt="掩码图" class="result-img" />
                <p>掩码图</p>
              </div>
            </div>
            <div class="result-data">
              <p><strong>检测菜品：</strong>{{ getUniqueFoods(cameraDetectResult.detections).join('、') || '未检测到菜品' }}</p>
              <p><strong>菜品数量：</strong>{{ getUniqueFoods(cameraDetectResult.detections).length }}</p>
              <p :class="['waste-ratio', wasteRateClass(cameraDetectResult.wastage_rate)]"><strong>浪费率：</strong>{{ cameraDetectResult.wastage_rate }}%</p>
              <p><strong>状态：</strong>{{ cameraDetectResult.status }}</p>
              <p v-if="cameraDetectResult.waste_cause"><strong>弃因分析：</strong>
                <span :class="causeClass(cameraDetectResult.waste_cause)">{{ cameraDetectResult.waste_cause }}</span>
                <span v-if="cameraDetectResult.waste_cause_confidence" class="cause-conf">({{ (cameraDetectResult.waste_cause_confidence * 100).toFixed(1) }}%)</span>
              </p>
            </div>
          </div>
        </div>
        
        <div class="modal-footer">
          <button class="btn btn-outline" @click="closeCameraModal">关闭窗口</button>
        </div>
      </div>
    </div>

    <AppFooter />
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import axios from 'axios'
import { showToast } from '../toast.js'

// 基础变量
const singleFileInput = ref(null)
const batchFileInput = ref(null)
const selectedSingleFile = ref(null)
const selectedBatchFiles = ref([])
const singlePreviewUrl = ref('')
const batchPreviewUrls = ref([])
const singleResult = ref(null)
const batchResult = ref(null)
const batchPageResults = ref({})
const loading = ref(false)
const errorMsg = ref('')
const isBatchMode = ref(false)
const targetPage = ref(1)
const currentBatchId = ref(null)

// 摄像头变量
const cameraModalVisible = ref(false)
const cameraActive = ref(false)
const videoRef = ref(null)
const captureImage = ref('')
const cameraDetectResult = ref(null)
const cameraLoading = ref(false)
const cameraErrorMsg = ref('')
const autoCaptureActive = ref(false)
const captureInterval = ref(5)

let autoCaptureTimer = null
let mediaStream = null

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// 模式切换
const switchToSingleMode = () => {
  isBatchMode.value = false
  selectedBatchFiles.value = []
  batchResult.value = null
  batchPageResults.value = {}
  currentBatchId.value = null
  targetPage.value = 1
  if (batchFileInput.value) batchFileInput.value.value = ''
  errorMsg.value = ''
}

const switchToBatchMode = () => {
  isBatchMode.value = true
  selectedSingleFile.value = null
  singleResult.value = null
  targetPage.value = 1
  if (singleFileInput.value) singleFileInput.value.value = ''
  errorMsg.value = ''
}

// 弹窗控制
const openCameraModal = () => {
  cameraModalVisible.value = true
  cameraErrorMsg.value = ''
}

const closeCameraModal = () => {
  cameraModalVisible.value = false
  stopCamera()
  stopAutoCapture()
  if (captureImage.value) URL.revokeObjectURL(captureImage.value)
  captureImage.value = ''
  cameraDetectResult.value = null
  cameraErrorMsg.value = ''
}

// 摄像头开关
const toggleCamera = async () => {
  if (cameraActive.value) {
    stopCamera()
    cameraActive.value = false
    cameraErrorMsg.value = ''
    return
  }

  cameraLoading.value = true
  cameraErrorMsg.value = ''

  try {
    const getUserMedia = navigator.mediaDevices?.getUserMedia || 
                        navigator.getUserMedia || 
                        navigator.webkitGetUserMedia || 
                        navigator.mozGetUserMedia;

    if (!getUserMedia) throw new Error('浏览器不支持摄像头，请使用Chrome/Firefox最新版本')

    const constraints = { video: true, audio: false }
    mediaStream = await new Promise((resolve, reject) => {
      if (navigator.mediaDevices?.getUserMedia) {
        navigator.mediaDevices.getUserMedia(constraints).then(resolve).catch(reject)
      } else {
        getUserMedia.call(navigator, constraints, resolve, reject)
      }
    })

    if (videoRef.value) {
      videoRef.value.srcObject = mediaStream
      cameraActive.value = true
      cameraErrorMsg.value = ''
    } else {
      throw new Error('视频元素未找到，请刷新页面重试')
    }
  } catch (err) {
    console.error('摄像头错误：', err)
    let msg = '摄像头开启失败：'
    if (err.name === 'NotAllowedError') msg += '请在浏览器地址栏允许摄像头权限'
    else if (err.name === 'NotFoundError') msg += '未检测到摄像头设备'
    else if (err.name === 'NotSupportedError') msg += '仅支持localhost/HTTPS环境'
    else msg += err.message
    cameraErrorMsg.value = msg
    showToast(msg, 'error')
  } finally {
    cameraLoading.value = false
  }
}

// 停止摄像头
const stopCamera = () => {
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop())
    mediaStream = null
  }
  if (videoRef.value) videoRef.value.srcObject = null
  cameraActive.value = false
}

// 手动抓拍
const manualCapture = async () => {
  if (!cameraActive.value || !videoRef.value || cameraLoading.value) return
  
  cameraLoading.value = true
  cameraErrorMsg.value = ''
  
  try {
    const video = videoRef.value
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth || video.clientWidth
    canvas.height = video.videoHeight || video.clientHeight
    
    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    
    canvas.toBlob(async (blob) => {
      if (captureImage.value) URL.revokeObjectURL(captureImage.value)
      captureImage.value = URL.createObjectURL(blob)
      await detectCaptureImage(blob)
      cameraLoading.value = false
    }, 'image/jpeg', 0.8)
  } catch (err) {
    cameraErrorMsg.value = `抓拍失败：${err.message}`
    cameraLoading.value = false
  }
}

// 传送带模式
const toggleAutoCapture = () => {
  autoCaptureActive.value ? stopAutoCapture() : startAutoCapture()
}

const startAutoCapture = () => {
  if (!cameraActive.value || autoCaptureActive.value) return
  autoCaptureActive.value = true
  manualCapture()
  
  autoCaptureTimer = setInterval(() => {
    manualCapture()
  }, captureInterval.value * 1000)
}

const stopAutoCapture = () => {
  if (autoCaptureTimer) {
    clearInterval(autoCaptureTimer)
    autoCaptureTimer = null
  }
  autoCaptureActive.value = false
}

// 抓拍图片检测
const detectCaptureImage = async (blob) => {
  if (!blob) return
  cameraLoading.value = true
  cameraErrorMsg.value = ''
  cameraDetectResult.value = null
  
  try {
    const formData = new FormData()
    const file = new File([blob], `camera_capture_${Date.now()}.jpg`, { type: 'image/jpeg' })
    formData.append('file', file)
    formData.append('record_type', 'camera')
    
    const res = await axios.post(`${API_BASE_URL}/predict`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 3000000
    })
    
    if (res.data.success) {
      cameraDetectResult.value = res.data.data[0]
      showToast('检测完成', 'success')
    } else {
      cameraErrorMsg.value = res.data.message || '检测失败'
      showToast('检测失败', 'error')
    }
  } catch (err) {
    let msg = '检测失败：'
    if (err.message.includes('Network Error')) msg += '无法连接后端服务，请检查服务'
    else if (err.message.includes('timeout')) msg += '请求超时'
    else msg += err.response?.data?.detail || err.message
    cameraErrorMsg.value = msg
    showToast(msg, 'error')
  } finally {
    cameraLoading.value = false
  }
}

// 文件上传相关
const triggerFileSelect = () => {
  isBatchMode.value ? (batchFileInput.value?.click()) : (singleFileInput.value?.click())
}

const handleSingleFileSelect = (e) => {
  const file = e.target.files[0]
  if (file) {
    selectedSingleFile.value = file
    if (singlePreviewUrl.value) URL.revokeObjectURL(singlePreviewUrl.value)
    singlePreviewUrl.value = URL.createObjectURL(file)
    singleResult.value = null
    errorMsg.value = ''
  }
}

const handleBatchFileSelect = (e) => {
  const files = Array.from(e.target.files)
  if (files.length) {
    selectedBatchFiles.value = files
    batchPreviewUrls.value.forEach(u => URL.revokeObjectURL(u))
    batchPreviewUrls.value = files.slice(0, 6).map(f => URL.createObjectURL(f))
    batchResult.value = null
    batchPageResults.value = {}
    currentBatchId.value = null
    targetPage.value = 1
    errorMsg.value = ''
  }
}

// 拖拽上传
const handleDrop = (e) => {
  const files = Array.from(e.dataTransfer.files || [])
  if (!files.length) return
  const imageFiles = files.filter(f => f.type.startsWith('image/'))
  if (!imageFiles.length) {
    errorMsg.value = '请拖入图片文件（PNG/JPG/BMP/WEBP）'
    return
  }
  if (isBatchMode.value) {
    selectedBatchFiles.value = imageFiles
    batchPreviewUrls.value.forEach(u => URL.revokeObjectURL(u))
    batchPreviewUrls.value = imageFiles.slice(0, 6).map(f => URL.createObjectURL(f))
    batchResult.value = null
    batchPageResults.value = {}
    currentBatchId.value = null
    targetPage.value = 1
  } else {
    selectedSingleFile.value = imageFiles[0]
    if (singlePreviewUrl.value) URL.revokeObjectURL(singlePreviewUrl.value)
    singlePreviewUrl.value = URL.createObjectURL(imageFiles[0])
    singleResult.value = null
  }
  errorMsg.value = ''
}

// 弃因分类颜色
const causeClass = (cause) => {
  const map = {
    '正常范围': 'cause-normal',
    '份量过大': 'cause-excess',
    '口味偏好/菜品质量': 'cause-taste',
    '油腻不适': 'cause-oily',
    '无餐盘/空盘': 'cause-empty'
  }
  return map[cause] || ''
}

// 浪费率动态颜色（低<20绿 / 中20-50橙 / 高≥50红）
const wasteRateClass = (rate) => {
  if (rate < 20) return 'waste-low'
  if (rate < 50) return 'waste-mid'
  return 'waste-high'
}

// 兼容所有数据结构
const getUniqueFoods = (detectionsOrItems) => {
  if (!detectionsOrItems || !Array.isArray(detectionsOrItems)) return []
  const foodNames = detectionsOrItems
    .map(d => d.food_name || d.class_name || '')
    .filter(name => name.trim() !== '' && name !== '?')
  return [...new Set(foodNames)]
}

const handleError = (err) => {
  errorMsg.value = err.response?.data?.detail || (err.message.includes('Network Error') ? '无法连接后端' : err.message)
}

const submitSingleToBackend = async () => {
  if (!selectedSingleFile.value) return
  loading.value = true
  errorMsg.value = ''
  singleResult.value = null

  try {
    const formData = new FormData()
    formData.append('file', selectedSingleFile.value)
    const res = await axios.post(`${API_BASE_URL}/predict`, formData, {
      headers: {'Content-Type': 'multipart/form-data'}, timeout: 3000000
    })
    if (res.data.success) {
      singleResult.value = res.data.data[0]
      showToast('检测完成', 'success')
    } else {
      errorMsg.value = res.data.message || '检测失败'
      showToast('检测失败', 'error')
    }
  } catch (err) { handleError(err) }
  finally { loading.value = false; if (singleFileInput.value) singleFileInput.value.value = '' }
}

// 批量检测
const submitBatchToBackend = async () => {
  if (!selectedBatchFiles.value.length) return
  loading.value = true
  errorMsg.value = ''
  batchResult.value = null
  batchPageResults.value = {}
  currentBatchId.value = null
  targetPage.value = 1

  try {
    const formData = new FormData()
    selectedBatchFiles.value.forEach(f => formData.append('files', f))
    const res = await axios.post(`${API_BASE_URL}/batch_predict`, formData, {
      headers: {'Content-Type': 'multipart/form-data'}, timeout: 180000
    })
    if (res.data.success) {
      batchResult.value = res.data
      currentBatchId.value = res.data.batch_id
      await getBatchPageResults(1)
      showToast('批量检测完成', 'success')
    } else {
      errorMsg.value = res.data.message || '批量检测失败'
      showToast('批量检测失败', 'error')
    }
  } catch (err) { handleError(err) }
  finally { loading.value = false; if (batchFileInput.value) batchFileInput.value.value = '' }
}

// 纯前端分页
const getBatchPageResults = async (page) => {
  if (!batchResult.value) {
    errorMsg.value = '请先完成批量检测'
    return
  }
  if (page < 1) return

  loading.value = true
  errorMsg.value = ''

  try {
    const allRecords = batchResult.value.records || []
    const pageSize = 3
    const totalRecords = allRecords.length
    const totalPages = Math.ceil(totalRecords / pageSize)

    const start = (page - 1) * pageSize
    const currentPageRecords = allRecords.slice(start, start + pageSize)

    batchPageResults.value = {
      success: true,
      data: {
        records: currentPageRecords,
        pagination: {
          page: page,
          page_size: pageSize,
          total: totalRecords,
          total_pages: totalPages,
          has_prev: page > 1,
          has_next: page < totalPages
        }
      }
    }
    targetPage.value = page
  } catch (err) {
    handleError(err)
  } finally {
    loading.value = false
  }
}

const jumpToTargetPage = () => {
  if (!targetPage.value) return
  const currentPage = batchPageResults.value.data?.pagination?.page
  if (currentPage && targetPage.value !== currentPage) {
    getBatchPageResults(targetPage.value)
  }
}

const changeBatchPage = (page) => {
  if (page < 1) return
  getBatchPageResults(page)
}

// 页面清理
onUnmounted(() => {
  stopCamera()
  stopAutoCapture()
  if (captureImage.value) URL.revokeObjectURL(captureImage.value)
  if (singlePreviewUrl.value) URL.revokeObjectURL(singlePreviewUrl.value)
  batchPreviewUrls.value.forEach(u => URL.revokeObjectURL(u))
})
</script>

<style scoped>
/* 基础样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
}

.app-container {
  min-height: 100vh;
  background-color: #f8faff;
  display: flex;
  flex-direction: column;
}

.nav-link.active {
  background-color: #4f46e5;
  color: #ffffff; 
  border-color: #4f46e5;
  box-shadow: 0 4px 8px rgba(79, 70, 229, 0.2);
}

/* 响应式适配 */
@media (max-width: 768px) {
  
  
  
}

.main-content {
  flex: 1;
  padding: 30px 20px;
}

.hero-section {
  text-align: center;
  margin-bottom: 24px;
}

.hero-title {
  font-size: 40px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 10px;
  letter-spacing: 1px;
}

.hero-subtitle {
  font-size: 20px;
  font-weight: 600;
  color: #6366f1;
  margin-bottom: 16px;
}

.hero-desc {
  font-size: 16px;
  color: #64748b;
  max-width: 600px;
  margin: 0 auto 24px;
}

.hero-buttons {
  display: flex;
  gap: 14px;
  justify-content: center;
  flex-wrap: wrap;
}

.btn {
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
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

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 上传区域 */
.upload-section {
  display: flex;
  justify-content: center;
}

.upload-card {
  width: 100%;
  max-width: 1400px;
  background: #fff;
  border: 2px dashed #c7d2fe;
  border-radius: 16px;
  padding: 24px 20px;
  text-align: center;
}

.upload-icon {
  font-size: 26px;
  color: #818cf8;
}

.upload-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 10px 0;
}

.upload-desc {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 20px;
}

.button-group {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.select-btn, .detect-btn {
  width: 220px;
  padding: 12px 0;
  font-size: 16px;
}

.file-tip {
  font-size: 14px;
  color: #64748b;
  margin: 10px 0;
}

.file-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin: 10px 0;
}

.preview-thumbs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.preview-thumb {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

/* 图片区域 */
.result-images {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin: 16px 0;
  width: 100%;
  margin-bottom: 30px;
}

.img-item {
  width: 100%;
  height: 220px;
  display: flex;
  flex-direction: column;
  border: none !important;
  background: none !important;
  padding: 0 !important;
}

.result-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 8px;
  border: none !important;
  box-shadow: none !important;
  background-color: #f8f9fa;
}

.img-item p {
  margin-top: 6px;
  font-size: 14px;
  color: #64748b;
  text-align: center;
}

/* 检测数据 */
.result-data {
  color: #64748b;
  line-height: 1.6;
  margin-top: 0;
  border-top: none !important;
  padding-top: 0 !important;
}

.single-result {
  margin-top: 20px;
  padding: 16px;
  background: #f0f4ff;
  border-radius: 8px;
  text-align: left;
  border: 1px solid #c7d2fe;
}

.waste-ratio {
  font-weight: bold;
}
.waste-low { color: #10b981; }
.waste-mid { color: #f59e0b; }
.waste-high { color: #ef4444; }

/* 弃因标签样式（徽章） */
.cause-normal {
  background: #ecfdf5; color: #10b981; font-weight: 500;
  padding: 2px 12px; border-radius: 12px;
}

.cause-excess {
  background: #fffbeb; color: #f59e0b; font-weight: 500;
  padding: 2px 12px; border-radius: 12px;
}

.cause-taste {
  background: #fef2f2; color: #ef4444; font-weight: 500;
  padding: 2px 12px; border-radius: 12px;
}

.cause-oily {
  background: #f1f5f9; color: #64748b; font-weight: 500;
  padding: 2px 12px; border-radius: 12px;
}

.cause-empty {
  background: #eff6ff; color: #3b82f6; font-weight: 500;
  padding: 2px 12px; border-radius: 12px;
}

.cause-conf {
  color: #909399;
  font-size: 13px;
  margin-left: 4px;
}

.batch-summary {
  margin-bottom: 16px;
}

.batch-results {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.fail-card {
  padding: 20px;
  background: #fef0f0;
  border-radius: 8px;
  border: 1px solid #f56c6c;
}

.error-text {
  color: #ef4444;
  font-weight: 500;
}

/* 分页 */
.pagination {
  display: flex;
  gap: 14px;
  justify-content: center;
  align-items: center;
  margin: 20px 0;
  flex-wrap: wrap;
}

.page-select-container {
  display: flex;
  align-items: center;
}

.page-select {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #6366f1;
  color: #6366f1;
  background: #fff;
  font-size: 14px;
  cursor: pointer;
  margin: 0 4px;
}

.page-info {
  font-size: 14px;
  color: #64748b;
  white-space: nowrap;
}

.page-btn {
  padding: 6px 12px;
  font-size: 14px;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-tip {
  margin-top: 20px;
  color: #6366f1;
}

.error-tip {
  margin-top: 20px;
  color: #f56c6c;
  padding: 10px;
  background: #fef0f0;
  border-radius: 6px;
}

/* 摄像头弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  background: #fff;
  border-radius: 12px;
  width: 100%;
  max-width: 1000px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  color: #1e293b;
  font-size: 18px;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #64748b;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.modal-close:hover {
  background: #f0f4ff;
  color: #6366f1;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid #eee;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* 摄像头控制面板 */
.camera-control-panel {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.auto-capture-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.interval-setting {
  display: flex;
  gap: 8px;
  align-items: center;
}

.interval-input {
  width: 60px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid #6366f1;
  color: #6366f1;
  text-align: center;
}

/* 摄像头预览 */
.camera-preview-container {
  display: flex;
  gap: 20px;
  margin: 20px 0;
  flex-wrap: wrap;
}

/* 隐藏样式：仅隐藏，不销毁元素 */
.hidden {
  display: none !important;
}

.camera-preview {
  flex: 1;
  min-width: 600px;
  width: 100%;
  height: auto;
  border-radius: 8px;
  background: #000;
}

.capture-preview-box {
  width: 200px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.capture-preview-img {
  width: 100%;
  height: auto;
  border-radius: 8px;
  border: 1px solid #c7d2fe;
}

.camera-tip {
  text-align: center;
  color: #64748b;
  padding: 20px;
}

.camera-result-section {
  margin-top: 20px;
}

/* 页脚 */

/* 页脚链接样式 */

.footer-list a {
  text-decoration: none;
  color: #64748b;
  transition: color 0.2s;
}

.footer-list a:hover {
  color: #4f46e5;
}

/* 响应式 */
@media (max-width: 992px) {
  .batch-results {
    grid-template-columns: repeat(2, 1fr);
  }
  .img-item {
    height: 180px;
  }
  .camera-preview {
    min-width: 100%;
  }
  .capture-preview-box {
    width: 100%;
  }
}

@media (max-width: 768px) {
  .batch-results {
    grid-template-columns: 1fr;
  }
  .img-item {
    height: 200px;
  }
  .result-images {
    gap: 8px;
    margin-bottom: 25px;
  }
  .pagination {
    gap: 8px;
  }
  .page-select {
    padding: 4px 8px;
    font-size: 13px;
  }
  
  
  
}
</style>