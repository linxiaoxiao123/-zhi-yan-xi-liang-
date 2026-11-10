<template>
  <footer class="app-footer">
    <div class="footer-container">
      <div class="footer-col">
        <div class="footer-logo">
          <span class="logo-icon">🍴</span>
          <span>智眼惜粮——食堂餐食浪费智能监测与分析系统</span>
        </div>
        <p class="footer-desc">
          利用AI视觉识别技术，精准监测食堂剩餐情况，助力餐饮精细化管理，减少食物浪费。
        </p>
      </div>
      <div class="footer-col">
        <h4 class="footer-col-title">快速链接</h4>
        <ul class="footer-list">
          <li><router-link to="/" class="footer-link">检测首页</router-link></li>
          <li><router-link to="/detection-record" class="footer-link">检测记录</router-link></li>
          <li><router-link to="/data-summary" class="footer-link">数据汇总</router-link></li>
          <li><router-link to="/judge-scoring" class="footer-link">评委打分</router-link></li>
          <li><router-link to="/system-settings" class="footer-link">系统设置</router-link></li>
        </ul>
      </div>
      <div class="footer-col">
        <h4 class="footer-col-title">联系我们</h4>
        <ul class="footer-list contact-list">
          <li>📧 example@example.com</li>
          <li>📞 +86-XXX-XXXX-XXXX</li>
          <li>📍 中国·XX省·XX市</li>
        </ul>
      </div>
    </div>
  </footer>
</template>

<script setup>
</script>

<style scoped>
.app-footer {
  background: #fff;
  padding: 30px 40px;
  margin-top: auto;
  border-top: 1px solid #e2e8f0;
}
.footer-container {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 30px;
  max-width: 1400px;
  margin: 0 auto;
}
.footer-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.footer-logo {
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
.footer-desc {
  font-size: 14px;
  color: #64748b;
  line-height: 1.5;
}
.footer-col-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 8px;
}
.footer-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.footer-link {
  text-decoration: none;
  color: #64748b;
  transition: color 0.2s;
}
.footer-link:hover {
  color: #4f46e5;
}
.contact-list {
  gap: 12px;
  color: #64748b;
}
@media (max-width: 768px) {
  .footer-container {
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
}
</style>
