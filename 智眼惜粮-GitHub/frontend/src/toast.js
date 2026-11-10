import { reactive } from 'vue'

// 全局 Toast 状态（跨组件共享）
const state = reactive({
  toasts: []
})

let id = 0

export function showToast(message, type = 'info', duration = 3000) {
  const toastId = ++id
  state.toasts.push({ id: toastId, message, type })
  setTimeout(() => {
    const idx = state.toasts.findIndex(t => t.id === toastId)
    if (idx !== -1) state.toasts.splice(idx, 1)
  }, duration)
}

export default state
