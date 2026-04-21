<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'

const store = useWorkspaceStore()

// JSON 预览用于和 Apifox 对照调试，也方便后续前端接入时复用同一份请求结构。
async function copyPayload() {
  await navigator.clipboard.writeText(store.payloadJson)
  ElMessage.success('请求体已复制')
}
</script>

<template>
  <section class="panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Payload</p>
        <h2>请求体预览</h2>
      </div>
      <el-button round @click="copyPayload">复制 JSON</el-button>
    </div>
    <pre class="json-preview">{{ store.payloadJson }}</pre>
  </section>
</template>
