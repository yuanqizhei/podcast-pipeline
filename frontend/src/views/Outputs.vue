<template>
  <div class="page">
    <div class="page-title"><el-icon><Headset /></el-icon>产物输出</div>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <div>
          <span>成品</span>
          <el-button style="float: right" size="small" :icon="Refresh" circle title="刷新" @click="load" />
        </div>
      </template>
      <el-table :data="finals" size="default">
        <el-table-column prop="episode" label="剧集" width="160">
          <template #default="{ row }"><span class="mono">{{ row.episode }}</span></template>
        </el-table-column>
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ fmtSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ new Date(row.mtime * 1000).toLocaleString("zh-CN", { hour12: false }) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="260">
          <template #default="{ row }">
            <el-button size="small" :icon="VideoPlay" @click="playing = row">试听</el-button>
            <el-button size="small" :icon="Download" tag="a" :href="`/audio/output/${row.name}`" :download="row.name">
              下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="playing" class="player-bar">
        <span class="mono">{{ playing.name }}</span>
        <audio :src="`/audio/output/${playing.name}`" controls autoplay style="width: 100%"></audio>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span>中间产物</span></template>
      <el-table :data="intermediates" size="small">
        <el-table-column prop="name" label="文件" min-width="220">
          <template #default="{ row }"><span class="mono">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="{ voice_track: 'primary', beds: 'success', timeline: 'info' }[row.kind]">
              {{ row.kind }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ fmtSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button v-if="row.kind !== 'beds' && row.kind !== 'timeline'" size="small" :icon="VideoPlay"
              @click="playing = { name: row.name }">试听</el-button>
            <el-button v-else size="small" :icon="View" tag="a" :href="`/audio/output/${row.name}`" target="_blank">
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header><span>语音缓存管理（audio/segments/）</span></template>
      <div class="seg-bar">
        <el-select v-model="segEpisode" style="width: 200px" placeholder="选择剧集" @change="loadSegs">
          <el-option v-for="n in episodeNames" :key="n" :label="n" :value="n" />
        </el-select>
        <el-button v-if="segs.length" type="danger" plain :icon="Delete" @click="clearAll">清空该集缓存</el-button>
        <el-popconfirm
          v-if="segs.length"
          title="清理孤儿缓存？删除当前脚本已不再引用的旧段落（改稿残留）"
          @confirm="prune"
        >
          <template #reference>
            <el-button plain :icon="Brush">清理孤儿缓存</el-button>
          </template>
        </el-popconfirm>
        <span class="hint">改稿后仅需重合成变化段落；删除单段可强制下次重新合成该段。</span>
      </div>
      <el-table :data="segs" size="small" max-height="360">
        <el-table-column prop="id" label="段 ID" width="100">
          <template #default="{ row }"><span class="mono">{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="hash" label="内容哈希" min-width="180">
          <template #default="{ row }"><span class="mono">{{ row.hash || "-" }}</span></template>
        </el-table-column>
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ fmtSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ new Date(row.mtime * 1000).toLocaleString("zh-CN", { hour12: false }) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button size="small" :icon="VideoPlay" @click="playing = { name: `segments/${segEpisode}/${row.id}.mp3` }">
              试听
            </el-button>
            <el-popconfirm
              :title="`重合成 ${row.id}？将删除该段缓存并自动提交 tts 任务（其余段落走缓存）`"
              @confirm="resynthesize(row)"
            >
              <template #reference>
                <el-button size="small" type="primary" :icon="RefreshRight" plain :loading="resyn === row.id">
                  重合成
                </el-button>
              </template>
            </el-popconfirm>
            <el-popconfirm :title="`删除 ${row.id}？下次构建将重新合成`" @confirm="removeSeg(row)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete" plain />
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="playing && playing.name.startsWith('segments/')" class="player-bar">
        <span class="mono">{{ playing.name }}</span>
        <audio :src="`/audio/${playing.name}`" controls autoplay style="width: 100%"></audio>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { Brush, Delete, Download, Refresh, RefreshRight, VideoPlay, View } from "@element-plus/icons-vue"
import api from "../api"

const finals = ref([])
const intermediates = ref([])
const episodeNames = ref([])
const segEpisode = ref("")
const segs = ref([])
const playing = ref(null)
const resyn = ref("")

function fmtSize(n) {
  if (n > 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB"
  return Math.round(n / 1024) + " KB"
}

async function load() {
  try {
    const [outs, scripts] = await Promise.all([api.listOutputs(), api.listScripts()])
    finals.value = outs.finals
    intermediates.value = outs.intermediates
    episodeNames.value = scripts.map((s) => s.name)
    if (!segEpisode.value && episodeNames.value.length) {
      segEpisode.value = episodeNames.value[0]
      loadSegs()
    }
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function loadSegs() {
  if (!segEpisode.value) return
  try {
    segs.value = await api.listSegments(segEpisode.value)
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function clearAll() {
  try {
    await api.clearSegments(segEpisode.value)
    ElMessage.success("已清空")
    loadSegs()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function prune() {
  try {
    const res = await api.pruneSegments(segEpisode.value)
    ElMessage.success(res.removed ? `已清理 ${res.removed} 个孤儿缓存段` : "没有孤儿缓存")
    loadSegs()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function removeSeg(row) {
  try {
    await api.deleteSegment(segEpisode.value, row.id)
    ElMessage.success(`已删除 ${row.id}`)
    loadSegs()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function resynthesize(row) {
  resyn.value = row.id
  try {
    await api.deleteSegment(segEpisode.value, row.id)
    const job = await api.createJob({ script: segEpisode.value, command: "tts" })
    ElMessage.success(`已提交重合成任务（${job.job.id}），可在"构建任务"页查看进度`)
    loadSegs()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
    loadSegs()
  } finally {
    resyn.value = ""
  }
}

onMounted(load)
</script>

<style scoped>
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
.seg-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
</style>
