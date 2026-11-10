<template>
  <div class="app-container">
    <router-view />
    <AiChat />
    <Toast />
  </div>
</template>

<script setup>
import AiChat from './components/AiChat.vue'
import Toast from './components/Toast.vue'
</script>

<style>
.app-container {
  height: 100%;
}
</style>