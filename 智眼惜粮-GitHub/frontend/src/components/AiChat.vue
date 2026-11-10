<template>
  <div class="ai-chat-wrapper">
    <!-- 悬浮球 -->
    <button v-if="!open" class="chat-fab" @click="open = true" title="AI 餐食分析助手">
      🤖
    </button>

    <!-- 对话窗口 -->
    <div v-if="open" class="chat-panel">
      <div class="chat-header">
        <span class="chat-title">🤖 AI 餐食分析助手</span>
        <button class="chat-close" @click="open = false">×</button>
      </div>
      <div class="chat-body" ref="bodyRef">
        <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
          <div class="bubble">{{ m.content }}</div>
        </div>
        <div v-if="loading" class="msg assistant">
          <div class="bubble typing">正在分析中…</div>
        </div>
      </div>
      <div class="chat-input">
        <input
          v-model="input"
          @keyup.enter="send"
          placeholder="问我：今天哪个菜浪费最狠？"
          :disabled="loading"
        />
        <button @click="send" :disabled="loading || !input.trim()">发送</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const open = ref(false)
const input = ref('')
const loading = ref(false)
const bodyRef = ref(null)
const messages = ref([
  { role: 'assistant', content: '你好，我是餐食浪费分析助手。可以问我浪费概况、哪个菜浪费最狠、趋势等，我会调用真实检测数据回答。' }
])

const scrollToBottom = async () => {
  await nextTick()
  if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
}

const send = async () => {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  await scrollToBottom()
  try {
    const res = await axios.post(`${API_BASE_URL}/api/ai/chat`, { message: text }, { timeout: 120000 })
    if (res.data.success) {
      messages.value.push({ role: 'assistant', content: res.data.answer || '（无回复）' })
    } else {
      messages.value.push({ role: 'assistant', content: '出错了：' + (res.data.detail || '未知错误') })
    }
  } catch (err) {
    const msg = err.response?.data?.detail || err.message || '网络错误'
    messages.value.push({ role: 'assistant', content: '出错了：' + msg })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}
</script>

<style scoped>
.ai-chat-wrapper {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2000;
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
}
.chat-fab {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: none;
  background: #4f46e5;
  color: #fff;
  font-size: 32px;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4);
  transition: transform 0.2s;
}
.chat-fab:hover {
  transform: scale(1.08);
}
.chat-panel {
  width: 420px;
  height: 580px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: #4f46e5;
  color: #fff;
}
.chat-title {
  font-size: 16px;
  font-weight: 600;
}
.chat-close {
  background: none;
  border: none;
  color: #fff;
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
}
.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #f8fafc;
}
.msg {
  display: flex;
}
.msg.user {
  justify-content: flex-end;
}
.msg.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 80%;
  padding: 11px 15px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bubble {
  background: #4f46e5;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg.assistant .bubble {
  background: #fff;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 4px;
}
.typing {
  color: #64748b;
}
.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #e2e8f0;
  background: #fff;
}
.chat-input input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
}
.chat-input input:focus {
  border-color: #4f46e5;
}
.chat-input button {
  padding: 0 18px;
  border: none;
  border-radius: 8px;
  background: #4f46e5;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
}
.chat-input button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
