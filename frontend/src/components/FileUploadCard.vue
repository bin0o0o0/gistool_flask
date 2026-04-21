<script setup lang="ts">
import type { UploadRequestOptions } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import type { UploadKind } from '@/types'

const store = useWorkspaceStore()

// 三类基础文件共用一张上传卡：模板工程、流域边界、河流水系。
const uploadItems: Array<{
  kind: Exclude<UploadKind, 'station_excel'>
  title: string
  hint: string
  accept: string
  multiple: boolean
}> = [
  {
    kind: 'template_project',
    title: 'ArcGIS Pro 模板',
    hint: '上传 .aprx 模板工程',
    accept: '.aprx',
    multiple: false
  },
  {
    kind: 'basin_boundary',
    title: '流域边界',
    hint: '支持 GeoJSON、KML；Shapefile 可一次多选 shp/shx/dbf/prj',
    accept: '.geojson,.json,.kml,.zip,.shp,.shx,.dbf,.prj,.cpg,.sbn,.sbx,.qix,.xml',
    multiple: true
  },
  {
    kind: 'river_network',
    title: '河流水系',
    hint: '支持 GeoJSON、KML；Shapefile 可一次多选 shp/shx/dbf/prj',
    accept: '.geojson,.json,.kml,.zip,.shp,.shx,.dbf,.prj,.cpg,.sbn,.sbx,.qix,.xml',
    multiple: true
  }
]

async function handleUpload(kind: Exclude<UploadKind, 'station_excel'>, files: File[]) {
  await store.uploadDataFiles(kind, files)
  if (!store.error) {
    ElMessage.success('文件上传成功')
  } else {
    ElMessage.error(store.uploads[kind].error || store.error)
  }
}

function uploadRequest(kind: Exclude<UploadKind, 'station_excel'>) {
  // Element Plus 需要一个固定函数引用，这里用闭包把当前文件类型带进去。
  return (options: UploadRequestOptions) => handleUpload(kind, [options.file])
}

function openFilePicker(kind: Exclude<UploadKind, 'station_excel'>) {
  document.getElementById(inputId(kind))?.click()
}

function inputId(kind: Exclude<UploadKind, 'station_excel'>) {
  return `upload-input-${kind}`
}

function handleNativeSelection(kind: Exclude<UploadKind, 'station_excel'>, event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length > 0) {
    void handleUpload(kind, files)
  }
  // 清空 value 后，用户再次选择同一组文件也能触发 change。
  input.value = ''
}

function buttonLabel(kind: Exclude<UploadKind, 'station_excel'>) {
  const state = store.uploads[kind]
  if (state.uploading) return '上传中...'
  if (kind === 'basin_boundary') return '添加流域面'
  if (kind === 'river_network') return '添加河流水系'
  return state.result ? '重新选择文件' : '选择文件'
}

function uploadedDatasetCount(kind: Exclude<UploadKind, 'station_excel'>) {
  if (kind === 'basin_boundary') return store.form.inputs.basin_boundaries.length
  if (kind === 'river_network') return store.form.inputs.river_networks.length
  return store.uploads[kind].result ? 1 : 0
}

function isUploadReady(kind: Exclude<UploadKind, 'station_excel'>) {
  return uploadedDatasetCount(kind) > 0
}
</script>

<template>
  <section class="panel">
    <p class="eyebrow">Step 1: Data</p>
    <h2>上传基础数据</h2>
    <p class="panel-copy">浏览器不会直接暴露本机绝对路径，所以先上传到后端，再由 ArcPy 使用保存后的路径。</p>

    <div class="upload-grid">
      <div v-for="item in uploadItems" :key="item.kind" class="upload-card">
        <div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.hint }}</p>
          <small v-if="item.kind !== 'template_project' && uploadedDatasetCount(item.kind) > 0" class="upload-count">
            已添加 {{ uploadedDatasetCount(item.kind) }} 个图层
          </small>
        </div>
        <el-upload
          v-if="!item.multiple"
          action="#"
          :accept="item.accept"
          :show-file-list="false"
          :http-request="uploadRequest(item.kind)"
        >
          <el-button
            :type="isUploadReady(item.kind) ? 'success' : 'primary'"
            :loading="store.uploads[item.kind].uploading"
            round
          >
            {{ buttonLabel(item.kind) }}
          </el-button>
        </el-upload>
        <div v-else>
          <input
            :id="inputId(item.kind)"
            class="native-file-input"
            type="file"
            :accept="item.accept"
            multiple
            @change="handleNativeSelection(item.kind, $event)"
          />
          <el-button
            :type="isUploadReady(item.kind) ? 'success' : 'primary'"
            :loading="store.uploads[item.kind].uploading"
            round
            @click="openFilePicker(item.kind)"
          >
            {{ buttonLabel(item.kind) }}
          </el-button>
          <p class="upload-help">Shapefile 至少同时选择 .shp、.shx、.dbf。</p>
        </div>
        <div v-if="item.kind === 'template_project' && store.uploads[item.kind].result" class="upload-status upload-status--success">
          <el-tag type="success" size="small">已上传</el-tag>
          <strong>{{ store.uploads[item.kind].result?.original_name }}</strong>
          <small class="path-text">保存路径：{{ store.uploads[item.kind].result?.path }}</small>
        </div>
        <div v-if="item.kind === 'basin_boundary' && store.form.inputs.basin_boundaries.length" class="dataset-list">
          <div v-for="layer in store.form.inputs.basin_boundaries" :key="layer.id" class="dataset-row">
            <span>{{ layer.name }}</span>
            <button type="button" @click="store.removeBasinLayer(layer.id)">移除</button>
          </div>
        </div>
        <div v-if="item.kind === 'river_network' && store.form.inputs.river_networks.length" class="dataset-list">
          <div v-for="layer in store.form.inputs.river_networks" :key="layer.id" class="dataset-row">
            <span>{{ layer.name }}</span>
            <button type="button" @click="store.removeRiverLayer(layer.id)">移除</button>
          </div>
        </div>
        <el-alert
          v-if="store.uploads[item.kind].error"
          :title="store.uploads[item.kind].error"
          type="error"
          show-icon
          :closable="false"
        />
      </div>
    </div>
  </section>
</template>
