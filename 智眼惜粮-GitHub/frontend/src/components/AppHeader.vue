<template>
  <header class="app-header">
    <div class="logo">
      <span class="logo-icon">🍴</span>
      <span>智眼惜粮——食堂餐食浪费智能监测与分析系统</span>
    </div>
    <nav class="nav">
      <router-link to="/" class="nav-link" :class="{ active: $route.name === 'Home' }">检测首页</router-link>
      <router-link to="/detection-record" class="nav-link" :class="{ active: $route.name === 'DetectionRecord' }">检测记录</router-link>
      <router-link to="/data-summary" class="nav-link" :class="{ active: $route.name === 'DataSummary' }">数据汇总</router-link>
      <router-link to="/judge-scoring" class="nav-link" :class="{ active: $route.name === 'JudgeScoring' }">评委打分</router-link>
      <router-link to="/system-settings" class="nav-link" :class="{ active: $route.name === 'SystemSettings' }">系统设置</router-link>
    </nav>
    <slot name="actions"></slot>
  </header>
</template>

<script setup>
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 40px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  gap: 20px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}
.logo-icon {
  font-size: 20px;
  color: #6366f1;
}
.nav {
  display: flex;
  gap: 12px;
  flex: 1;
  justify-content: center;
  flex-wrap: wrap;
}
.nav-link {
  text-decoration: none;
  color: #4f46e5;
  font-size: 15px;
  font-weight: bold;
  padding: 8px 16px;
  border: 2px solid #4f46e5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  background: #fff;
}
.nav-link:hover {
  background: #f0f4ff;
  color: #3730a3;
  border-color: #3730a3;
  transform: translateY(-2px);
}
.nav-link.active {
  background: #4f46e5;
  color: #fff;
  border-color: #4f46e5;
  box-shadow: 0 4px 8px rgba(79, 70, 229, 0.2);
}
@media (max-width: 768px) {
  .app-header {
    padding: 12px 20px;
    flex-wrap: wrap;
  }
  .nav {
    gap: 8px;
    width: 100%;
    justify-content: center;
  }
  .nav-link {
    font-size: 13px;
    padding: 6px 10px;
  }
}
</style>
