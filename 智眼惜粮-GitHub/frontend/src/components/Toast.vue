<template>
  <div class="toast-container">
    <transition-group name="toast">
      <div v-for="t in toastState.toasts" :key="t.id" :class="['toast', t.type]">
        {{ t.message }}
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import toastState from '../toast.js'
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 3000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  pointer-events: none;
}
.toast {
  padding: 10px 22px;
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
  white-space: nowrap;
}
.toast.success { background: #10b981; }
.toast.error { background: #ef4444; }
.toast.info { background: #6366f1; }
.toast.warning { background: #f59e0b; }

.toast-enter-active, .toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from, .toast-leave-to {
  opacity: 0;
  transform: translateY(-12px);
}
</style>
