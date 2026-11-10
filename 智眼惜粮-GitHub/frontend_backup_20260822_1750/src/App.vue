<template>
  <div class="app-container">
    <router-view />
    <AiChat />
  </div>
</template>

<script setup>
import AiChat from './components/AiChat.vue'
</script>

<style>
.app-container {
  height: 100%;
}
</style>