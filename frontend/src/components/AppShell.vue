<script setup lang="ts">
// 页面外壳只负责品牌、说明和插槽布局；具体业务面板都由 WorkspaceView 组合。
defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-mark">
        <div class="brand-mark__icon">GIS</div>
        <div>
          <p class="brand-mark__title">流域图出图工具</p>
          <p class="brand-mark__subtitle">ArcGIS Pro Render Workbench</p>
        </div>
      </div>
      <div class="topbar__hint">本机 Flask + ArcPy 服务</div>
    </header>

    <main class="app-main">
      <section class="page-heading">
        <div>
          <p class="eyebrow">ArcPy Map Composer</p>
          <h1>{{ title }}</h1>
        </div>
        <p>{{ description }}</p>
      </section>

      <slot />
    </main>
  </div>
</template>
