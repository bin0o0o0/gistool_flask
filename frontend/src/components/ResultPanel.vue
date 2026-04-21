<script setup lang="ts">
import { useWorkspaceStore } from '@/stores/workspace'

// 出图结果面板只负责触发渲染和展示 PNG；ArcPy 的真实状态与警告由后端返回。
const store = useWorkspaceStore()
</script>

<template>
  <section class="panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Render</p>
        <h2>出图结果</h2>
      </div>
      <el-button type="primary" round :loading="store.rendering" @click="store.submitRender">
        开始出图
      </el-button>
    </div>

    <el-alert v-if="store.error" :title="store.error" type="error" show-icon :closable="false" />

    <div v-if="store.renderResult" class="result-block">
      <el-tag :type="store.renderResult.status === 'succeeded' ? 'success' : 'danger'">
        {{ store.renderResult.status }}
      </el-tag>
      <p v-if="store.renderResult.elapsed_seconds">耗时：{{ store.renderResult.elapsed_seconds }} 秒</p>
      <p class="path-text">PNG：{{ store.renderResult.output_png }}</p>
      <p v-if="store.renderResult.result_json" class="path-text">结果：{{ store.renderResult.result_json }}</p>

      <el-alert
        v-for="warning in store.renderResult.warnings || []"
        :key="warning"
        :title="warning"
        type="warning"
        show-icon
        :closable="false"
      />

      <img v-if="store.previewImageUrl" class="render-image" :src="store.previewImageUrl" alt="出图结果" />
    </div>
    <div v-else class="empty-state">点击开始出图后，最终 PNG 会显示在这里。</div>
  </section>
</template>
