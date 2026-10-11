<template>
  <div class="shell">
    <a class="skip-link" href="#main-content">跳转到主要内容</a>
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">C</span>
        <div><strong>CloudAgent</strong><small>LOCAL SUPPORT LAB</small></div>
      </div>
      <div class="sidebar-mode">
        <span class="sidebar-mode-dot" aria-hidden="true"></span>
        <div><strong>本地演示环境</strong><small>Mock 模型 · 合成数据</small></div>
      </div>
      <nav aria-label="主导航">
        <RouterLink to="/">演示操作面板</RouterLink>
        <RouterLink to="/providers">模型与服务状态</RouterLink>
        <RouterLink to="/catalog">知识源与工具</RouterLink>
      </nav>
      <div class="sidebar-note">阶段 A · 仅限本机演示<br />不连接真实模型或业务数据</div>
    </aside>
    <main id="main-content" tabindex="-1"><RouterView /></main>
  </div>
</template>
