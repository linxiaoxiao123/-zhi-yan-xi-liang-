<template>
  <div class="judge-container">
    <AppHeader />

    <main class="main-content">
      <!-- 得分汇总面板 -->
      <div class="score-panel">
        <div class="score-card">
          <div class="score-item">
            <div class="score-icon">📝</div>
            <span class="score-label">已评数量</span>
            <span class="score-value">{{ scoreData.total }}</span>
          </div>
          <div class="score-item correct">
            <div class="score-icon">✅</div>
            <span class="score-label">判定正确</span>
            <span class="score-value">{{ scoreData.correct }}</span>
          </div>
          <div class="score-item incorrect">
            <div class="score-icon">❌</div>
            <span class="score-label">判定错误</span>
            <span class="score-value">{{ scoreData.incorrect }}</span>
          </div>
          <div class="score-item accuracy">
            <div class="score-icon">🎯</div>
            <span class="score-label">准确率</span>
            <span class="score-value">{{ scoreData.accuracy }}%</span>
          </div>
        </div>
        <div class="score-tip">
          点击图片可放大查看原图与检测结果，判定后即时生效
          <button class="btn-reset" @click="resetScoreDisplay">🔄 重置显示</button>
        </div>
      </div>

      <!-- 图片缩略图网格 -->
      <div class="gallery-grid" v-if="records.length">
        <div
          class="gallery-card"
          v-for="(rec, idx) in records"
          :key="rec.id"
          :class="{ 'evaluated-correct': rec.judge_result === 'correct', 'evaluated-incorrect': rec.judge_result === 'incorrect' }"
          @click="openDetail(rec, idx)"
        >
          <div class="card-image">
            <img
              :src="rec.original_image_url"
              :alt="rec.file_name"
              @error="e => e.target.src = 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22150%22><rect fill=%22%23eee%22 width=%22200%22 height=%22150%22/><text x=%22100%22 y=%2280%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%2214%22>图片加载失败</text></svg>'"
            />
            <div class="card-judge-badge" v-if="rec.judge_result">
              {{ rec.judge_result === 'correct' ? '✓ 正确' : '✗ 错误' }}
            </div>
          </div>
          <div class="card-info">
            <div class="card-foods">{{ rec.foods.slice(0, 4).join('、') || '未识别' }}<span v-if="rec.foods.length > 4">等{{ rec.foods.length }}种</span></div>
            <div class="card-meta">
              <span class="card-waste" :class="{ 'high-waste': rec.wastage_rate > 50 }">浪费率 {{ rec.wastage_rate }}%</span>
              <span class="card-time">{{ rec.create_time?.slice(0, 10) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="loading" class="loading-tip">🌀 加载中...</div>
      <div v-if="errorMsg" class="error-tip">❌ {{ errorMsg }}</div>
      <div v-if="!loading && !errorMsg && !records.length" class="empty-tip">暂无检测记录</div>

      <!-- 分页 -->
      <div class="pagination" v-if="pagination.total_pages > 1">
        <button class="btn btn-outline page-btn" @click="changePage(pagination.page - 1)" :disabled="pagination.page <= 1">← 上一页</button>
        <span class="page-info">第 {{ pagination.page }} / {{ pagination.total_pages }} 页（共 {{ pagination.total }} 条）</span>
        <button class="btn btn-outline page-btn" @click="changePage(pagination.page + 1)" :disabled="pagination.page >= pagination.total_pages">下一页 →</button>
      </div>
    </main>

    <!-- 图片详情弹窗 -->
    <div v-if="detailVisible" class="modal-overlay" @click="closeDetail">
      <div class="modal-content detail-modal" @click.stop>
        <div class="modal-header">
          <h3>{{ currentRecord.file_name }}</h3>
          <button class="modal-close" @click="closeDetail">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-images">
            <div class="detail-img-box">
              <img :src="currentRecord.original_image_url" alt="原图" />
              <p>原始图像</p>
            </div>
            <div class="detail-img-box">
              <img :src="currentRecord.result_image_url" alt="YOLO检测" />
              <p>YOLO 检测结果</p>
            </div>
            <div class="detail-img-box">
              <img :src="currentRecord.mask_image_url" alt="U-Net分割" />
              <p>U-Net 分割掩码</p>
            </div>
          </div>
          <div class="detail-info">
            <div class="detail-foods">
              <strong>识别菜品：</strong>
              {{ currentRecord.foods.join('、') || '未识别到菜品' }}
            </div>
            <div class="detail-meta">
              <span>浪费率：<strong :class="{ 'high-waste': currentRecord.wastage_rate > 50 }">{{ currentRecord.wastage_rate }}%</strong></span>
              <span>检测时间：{{ currentRecord.create_time }}</span>
              <span v-if="currentRecord.judge_result">
                当前判定：<strong :class="currentRecord.judge_result === 'correct' ? 'text-correct' : 'text-incorrect'">
                  {{ currentRecord.judge_result === 'correct' ? '正确' : '错误' }}
                </strong>
              </span>
              <span v-else>当前判定：<strong class="text-pending">未评定</strong></span>
            </div>
          </div>
        </div>
        <div class="modal-footer judge-footer-wrap">
          <div class="record-nav">
            <button class="btn btn-outline nav-btn" @click="goToPrev" :disabled="currentIndex <= 0">← 上一张</button>
            <span class="nav-info">{{ currentIndex + 1 }} / {{ records.length }}</span>
            <button class="btn btn-outline nav-btn" @click="goToNext" :disabled="currentIndex >= records.length - 1">下一张 →</button>
          </div>
          <div class="judge-actions">
            <span class="judge-question">请判定检测结果是否准确：</span>
            <button
              class="btn btn-correct"
              :class="{ active: currentRecord.judge_result === 'correct' }"
              @click="submitEvaluation(currentRecord, 'correct')"
              :disabled="submitting"
            >
              ✓ 检测正确
            </button>
            <button
              class="btn btn-incorrect"
              :class="{ active: currentRecord.judge_result === 'incorrect' }"
              @click="submitEvaluation(currentRecord, 'incorrect')"
              :disabled="submitting"
            >
              ✗ 检测错误
            </button>
          </div>
          <div v-if="lastRecordTip" class="last-record-tip">
            ⚠ 当前已是本页最后一条记录，请点击"下一页"继续评分
          </div>
        </div>
      </div>
    </div>

    <AppFooter />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const records = ref([])
const pagination = reactive({ page: 1, page_size: 20, total: 0, total_pages: 0 })
const scoreData = reactive({ total: 0, correct: 0, incorrect: 0, accuracy: 0 })
const loading = ref(false)
const errorMsg = ref('')
const detailVisible = ref(false)
const currentRecord = ref({})
const submitting = ref(false)

const fetchRecords = async (page = 1) => {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await axios.get(`${API_BASE_URL}/api/judge/records`, { params: { page, page_size: 20 } })
    if (res.data.success) {
      records.value = res.data.data.records
      Object.assign(pagination, res.data.data.pagination)
    }
  } catch (err) {
    errorMsg.value = '加载失败：' + (err.response?.data?.detail || err.message)
  } finally {
    loading.value = false
  }
}

const fetchScore = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/api/judge/score`)
    if (res.data.success) Object.assign(scoreData, res.data.data)
  } catch (err) {
    // 静默失败
  }
}

const openDetail = (rec, idx) => {
  currentRecord.value = rec
  currentIndex.value = idx
  detailVisible.value = true
}

const currentIndex = ref(-1)

const goToPrev = () => {
  lastRecordTip.value = false
  if (currentIndex.value > 0) {
    const prev = records.value[currentIndex.value - 1]
    if (prev) {
      currentIndex.value = currentIndex.value - 1
      currentRecord.value = prev
    }
  }
}

const goToNext = () => {
  lastRecordTip.value = false
  if (currentIndex.value < records.value.length - 1) {
    const next = records.value[currentIndex.value + 1]
    if (next) {
      currentIndex.value = currentIndex.value + 1
      currentRecord.value = next
    }
  }
}

const resetScoreDisplay = async () => {
  try {
    await axios.delete(`${API_BASE_URL}/api/judge/reset`)
  } catch (err) {
    errorMsg.value = '重置失败：' + (err.response?.data?.detail || err.message)
    return
  }
  scoreData.total = 0
  scoreData.correct = 0
  scoreData.incorrect = 0
  scoreData.accuracy = 0
  records.value = []
  pagination.page = 1
  pagination.total = 0
  pagination.total_pages = 0
  lastRecordTip.value = false
  detailVisible.value = false
}

const closeDetail = () => {
  detailVisible.value = false
  currentRecord.value = {}
  currentIndex.value = -1
}

const lastRecordTip = ref(false)

const submitEvaluation = async (rec, result) => {
  submitting.value = true
  lastRecordTip.value = false
  try {
    const res = await axios.post(`${API_BASE_URL}/api/judge/evaluate`, {
      record_id: rec.id,
      result: result
    })
    if (res.data.success) {
      rec.judge_result = result
      const idx = records.value.findIndex(r => r.id === rec.id)
      if (idx >= 0) records.value[idx].judge_result = result
      await fetchScore()
      // 自动跳转下一张
      if (currentIndex.value < records.value.length - 1) {
        goToNext()
      } else {
        lastRecordTip.value = true
      }
    }
  } catch (err) {
    errorMsg.value = '提交失败：' + (err.response?.data?.detail || err.message)
  } finally {
    submitting.value = false
  }
}

const changePage = (page) => {
  if (page < 1 || page > pagination.total_pages) return
  fetchRecords(page)
}

onMounted(() => {
  fetchRecords()
  fetchScore()
})
</script>

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
}

.judge-container {
  min-height: 100vh;
  background-color: #f8faff;
  display: flex;
  flex-direction: column;
}

/* Header */

.nav-link.active { background: #4f46e5; color: #fff; border-color: #4f46e5; box-shadow: 0 4px 8px rgba(79,70,229,0.2); }

/* Main */
.main-content { flex: 1; padding: 24px 20px; max-width: 1400px; margin: 0 auto; width: 100%; }

/* Score Panel */
.score-panel { margin-bottom: 24px; }
.score-card {
  display: flex; gap: 16px; background: #fff; border-radius: 12px;
  padding: 20px 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  justify-content: center; flex-wrap: wrap;
}
.score-item {
  text-align: center; padding: 8px 28px; border-right: 1px solid #eee;
}
.score-item:last-child { border-right: none; }
.score-icon { font-size: 24px; line-height: 1; margin-bottom: 8px; }
.score-label { display: block; font-size: 13px; color: #64748b; margin-bottom: 4px; }
.score-value { font-size: 28px; font-weight: 700; color: #1e293b; }
.score-item.correct .score-value { color: #22c55e; }
.score-item.incorrect .score-value { color: #ef4444; }
.score-item.accuracy .score-value { color: #6366f1; }
.score-tip { text-align: center; color: #94a3b8; font-size: 13px; margin-top: 10px; display: flex; align-items: center; justify-content: center; gap: 16px; }
.btn-reset { padding: 4px 12px; border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; color: #64748b; font-size: 12px; cursor: pointer; transition: all 0.2s; }
.btn-reset:hover { background: #fef2f2; color: #ef4444; border-color: #ef4444; }

/* Gallery Grid */
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}
.gallery-card {
  background: #fff; border-radius: 10px; overflow: hidden;
  cursor: pointer; transition: all 0.2s; border: 3px solid transparent;
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}
.gallery-card:hover { transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0,0,0,0.1); }
.gallery-card.evaluated-correct { border-color: #22c55e; }
.gallery-card.evaluated-incorrect { border-color: #ef4444; }
.card-image {
  position: relative; width: 100%; height: 160px; overflow: hidden; background: #f1f5f9;
}
.card-image img {
  width: 100%; height: 100%; object-fit: cover;
}
.card-judge-badge {
  position: absolute; top: 8px; right: 8px;
  padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; color: #fff;
}
.evaluated-correct .card-judge-badge { background: #22c55e; }
.evaluated-incorrect .card-judge-badge { background: #ef4444; }
.card-info { padding: 10px 12px; }
.card-foods { font-size: 13px; color: #334155; margin-bottom: 6px; line-height: 1.4; }
.card-meta { display: flex; justify-content: space-between; align-items: center; }
.card-waste { font-size: 13px; color: #e6a23c; font-weight: 600; }
.card-waste.high-waste { color: #ef4444; }
.card-time { font-size: 12px; color: #94a3b8; }

/* Detail Modal */
.detail-modal { max-width: 1000px; }
.detail-images { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.detail-img-box { text-align: center; }
.detail-img-box img { width: 100%; max-height: 380px; object-fit: contain; border-radius: 8px; background: #f8f9fa; }
.detail-img-box p { margin-top: 6px; font-size: 14px; color: #64748b; }
.detail-info { margin-top: 8px; }
.detail-foods { font-size: 15px; color: #334155; margin-bottom: 10px; line-height: 1.6; }
.detail-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 14px; color: #64748b; }
.text-correct { color: #22c55e; }
.text-incorrect { color: #ef4444; }
.text-pending { color: #94a3b8; }
.high-waste { color: #ef4444 !important; }

/* Judge Footer */
.judge-footer-wrap { display: flex; flex-direction: column; gap: 14px; }
.record-nav { display: flex; align-items: center; justify-content: center; gap: 16px; }
.nav-btn { padding: 8px 16px; font-size: 14px; }
.nav-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.nav-info { font-size: 14px; color: #64748b; min-width: 80px; text-align: center; }
.last-record-tip {
  background: #fef3c7; color: #b45309; padding: 10px 16px; border-radius: 8px;
  font-size: 14px; text-align: center;
}

/* Judge Actions */
.judge-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; justify-content: center; }
.judge-question { font-size: 15px; color: #334155; font-weight: 500; }
.btn-correct {
  background: #fff; color: #22c55e; border: 2px solid #22c55e;
  padding: 10px 22px; border-radius: 8px; font-size: 15px; font-weight: 600;
  cursor: pointer; transition: all 0.2s;
}
.btn-correct:hover, .btn-correct.active { background: #22c55e; color: #fff; }
.btn-incorrect {
  background: #fff; color: #ef4444; border: 2px solid #ef4444;
  padding: 10px 22px; border-radius: 8px; font-size: 15px; font-weight: 600;
  cursor: pointer; transition: all 0.2s;
}
.btn-incorrect:hover, .btn-incorrect.active { background: #ef4444; color: #fff; }
.btn-correct:disabled, .btn-incorrect:disabled { opacity: 0.5; cursor: not-allowed; }
.btn { padding: 10px 20px; border-radius: 6px; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s; }
.btn-outline { background: #fff; color: #6366f1; border: 1px solid #6366f1; }
.btn-outline:hover { background: #f0f4ff; }

/* Modal */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; z-index: 1000; padding: 20px; }
.modal-content { background: #fff; border-radius: 12px; width: 100%; max-height: 90vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.modal-header { padding: 16px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
.modal-header h3 { color: #1e293b; font-size: 18px; margin: 0; }
.modal-close { background: none; border: none; font-size: 22px; cursor: pointer; color: #64748b; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 50%; }
.modal-close:hover { background: #f0f4ff; color: #6366f1; }
.modal-body { padding: 20px; }
.modal-footer { padding: 16px 20px; border-top: 1px solid #eee; display: flex; justify-content: flex-end; gap: 12px; }

/* Pagination */
.pagination { display: flex; gap: 14px; justify-content: center; align-items: center; margin: 24px 0; }
.page-btn { padding: 8px 16px; font-size: 14px; }
.page-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.page-info { font-size: 14px; color: #64748b; }

/* Tips */
.loading-tip { text-align: center; color: #6366f1; padding: 40px; font-size: 16px; }
.error-tip { text-align: center; color: #f56c6c; padding: 20px; background: #fef0f0; border-radius: 8px; margin: 16px 0; }
.empty-tip { text-align: center; color: #64748b; padding: 60px; font-size: 16px; }

/* Footer */

/* Responsive */
@media (max-width: 1200px) { .gallery-grid { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 992px) { .gallery-grid { grid-template-columns: repeat(3, 1fr); } .detail-images { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 640px) { .detail-images { grid-template-columns: 1fr; } }
@media (max-width: 768px) {
  .gallery-grid { grid-template-columns: repeat(2, 1fr); }
  
  
  
  .score-card { padding: 12px; }
  .score-item { padding: 8px 16px; }
  .score-value { font-size: 22px; }
  
}
@media (max-width: 480px) { .gallery-grid { grid-template-columns: 1fr 1fr; } }
</style>
