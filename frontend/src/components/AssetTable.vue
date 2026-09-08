<template>
  <div>
    <div class="table-bar">
      <el-upload :show-file-list="false" :http-request="doUpload" accept=".mp3,.wav,.m4a,.ogg,.flac,.aac,.wma">
        <el-button type="primary" :icon="Upload" :loading="uploading">上传音频</el-button>
      </el-upload>
      <el-button :icon="Refresh" circle title="刷新" @click="load" />
      <span class="hint">文件名与脚本标注对应（如 music/bgm_intro.mp3 ⇄ @insert music/bgm_intro.mp3）</span>
    </div>

    <el-table :data="items" size="default" v-loading="loading">
      <el-table-column label="文件名" min-width="220">
        <template #default="{ row }"><span class="mono">{{ row.name }}</span></template>
      </el-table-column>
      <el-table-column label="大小" width="110">
        <template #default="{ row }">{{ fmtSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="时长" width="90">
        <template #default="{ row }">{{ row.duration != null ? row.duration + "s" : "-" }}</template>
      </el-table-column>
      <el-table-column label="修改时间" width="170">
        <template #default="{ row }">{{ new Date(row.mtime * 1000).toLocaleString("zh-CN", { hour12: false }) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" :icon="VideoPlay" @click="play(row)">试听</el-button>
          <el-popconfirm :title="`删除 ${row.name}？`" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" :icon="Delete" plain>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="playing" class="player-bar">
      <span class="mono">{{ playing.name }}</span>
      <audio :src="playing.url" controls autoplay style="width: 100%"></audio>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { Delete, Refresh, Upload, VideoPlay } from "@element-plus/icons-vue"
import api from "../api"

const props = defineProps({ kind: { type: String, required: true } })

const items = ref([])
const loading = ref(false)
const uploading = ref(false)
const playing = ref(null)

function fmtSize(n) {
  if (n > 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB"
  return Math.round(n / 1024) + " KB"
}

async function load() {
  loading.value = true
  try {
    items.value = await api.listAssets(props.kind)
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    loading.value = false
  }
}

function play(row) {
  playing.value = { name: row.name, url: `/audio/${props.kind}/${encodeURIComponent(row.name)}` }
}

async function remove(row) {
  try {
    await api.deleteAsset(props.kind, row.name)
    ElMessage.success("已删除")
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function doUpload(opt) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append("file", opt.file)
    const { default: axios } = await import("axios")
    await axios.post(`/api/assets/${props.kind}`, fd)
    ElMessage.success(`已上传 ${opt.file.name}`)
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    uploading.value = false
  }
}

defineExpose({ load })
</script>

<style scoped>
.table-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
.player-bar {
  margin-top: 14px;
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.player-bar span {
  font-size: 12px;
  color: #606266;
}
</style>
