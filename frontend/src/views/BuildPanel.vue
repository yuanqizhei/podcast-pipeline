<template>
  <div class="page">
    <div class="page-title"><el-icon><VideoPlay /></el-icon>构建任务</div>

    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="脚本">
          <el-select v-model="form.script" style="width: 180px" placeholder="选择脚本">
            <el-option v-for="s in scripts" :key="s.name" :label="s.name" :value="s.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="命令">
          <el-select v-model="form.command" style="width: 130px">
            <el-option label="build 全流程" value="build" />
            <el-option label="tts 合成" value="tts" />
            <el-option label="assemble 组装" value="assemble" />
            <el-option label="mix 终混" value="mix" />
          </el-select>
        </el-form-item>
        <el-form-item label="引擎">
          <el-radio-group v-model="form.provider" @change="providerTouched = true">
            <el-radio-button value="dryrun">dryrun 零成本</el-radio-button>
            <el-radio-button value="minimax">MiniMax</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="试听">
          <el-input-number v-model="form.limit" :min="0" :max="50" placeholder="前 N 段" style="width: 110px" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.force">强制重合成</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="CaretRight" :disabled="!form.script || !!activeJob" @click="submit">
            发起构建
          </el-button>
          <el-button v-if="activeJob" type="danger" plain :icon="CircleClose" @click="cancel">取消任务</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="activeJob" shadow="never" style="margin-bottom: 16px">
      <template #header>
        <div class="job-head">
          <span class="mono">#{{ activeJob.id }} · {{ activeJob.script }} · {{ activeJob.command }} · {{ activeJob.provider }}</span>
          <el-tag :type="statusType(activeJob.status)" size="small">{{ activeJob.status }}</el-tag>
        </div>
      </template>

      <div class="stage-row">
        <el-steps :active="stageIndex" align-center finish-status="success" style="flex: 1">
          <el-step title="TTS 合成" :description="stageDesc('tts')" />
          <el-step title="组装主轨" :description="stageDesc('assemble')" />
          <el-step title="终混出片" :description="stageDesc('mix')" />
        </el-steps>
      </div>

      <el-progress
        :percentage="overallPercent"
        :stroke-width="14"
        :status="activeJob.status === 'done' ? 'success' : activeJob.status === 'failed' ? 'exception' : undefined"
        style="margin: 14px 0"
      />

      <div class="log-box" ref="logBox">
        <div v-for="(l, i) in logs" :key="i" class="log-line" :class="logClass(l)">{{ fmtLog(l) }}</div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>任务历史</span>
        <el-button style="float: right" size="small" :icon="Refresh" circle @click="loadHistory" title="刷新" />
      </template>
      <el-table :data="history" size="small" highlight-current-row @current-change="showHistory">
        <el-table-column prop="id" label="ID" width="90">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column prop="script" label="脚本" width="130" />
        <el-table-column prop="command" label="命令" width="90" />
        <el-table-column prop="provider" label="引擎" width="90" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ duration(row) }}</template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { useRoute } from "vue-router"
import { ElMessage } from "element-plus"
import { CaretRight, CircleClose, Refresh } from "@element-plus/icons-vue"
import api from "../api"

const route = useRoute()

const scripts = ref([])
const history = ref([])
const activeJob = ref(null)
const logs = ref([])
const logBox = ref(null)
const form = reactive({
  script: route.query.script || "",
  command: "build",
  provider: "dryrun",
  limit: 0,
  force: false,
})

let es = null
let providerTouched = false

const stageWeight = { tts: 0.6, assemble: 0.05, mix: 0.35 }

const overallPercent = computed(() => {
  const job = activeJob.value
  if (!job) return 0
  if (job.status === "done") return 100
  if (job.status !== "running" || !job.stage) return 0
  const p = job.progress || {}
  let frac = 0
  if (job.stage === "tts" && p.total) frac = ((p.current || 0) - (p.cached ? 0 : 1)) / p.total
  else if (job.stage === "mix") frac = p.percent || 0
  else if (job.stage === "assemble") frac = 1
  const done = { tts: 0, assemble: stageWeight.tts, mix: stageWeight.tts + stageWeight.assemble }[job.stage] || 0
  return Math.min(100, Math.round((done + stageWeight[job.stage] * Math.max(0, Math.min(frac, 1))) * 100))
})

const stageIndex = computed(() => {
  const s = activeJob.value?.stage
  const st = activeJob.value?.status
  if (st === "done") return 3
  if (!s) return 0
  return { tts: 1, assemble: 2, mix: 2 }[s] || 0
})

function stageDesc(stage) {
  const job = activeJob.value
  if (!job) return ""
  const p = job.progress || {}
  if (job.stage === stage) {
    if (stage === "tts" && p.total) return `${p.current || 0}/${p.total} 段`
    if (stage === "mix" && p.percent != null) return `${Math.round(p.percent * 100)}%`
    if (stage === "assemble") return "进行中"
  }
  if (job.status === "done") return "完成"
  return ""
}

function statusType(s) {
  return { done: "success", failed: "danger", cancelled: "warning", running: "primary", queued: "info" }[s] || "info"
}

function duration(row) {
  if (!row.started_at) return "-"
  const end = row.finished_at || Date.now() / 1000
  const sec = Math.round(end - row.started_at)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m${sec % 60}s`
}

function logClass(l) {
  const m = l.message || ""
  if (m.includes("[error]")) return "error"
  if (m.includes("[warn]")) return "warn"
  return ""
}

function fmtLog(l) {
  const t = new Date(l.ts * 1000).toLocaleTimeString("zh-CN", { hour12: false })
  return `[${t}] ${l.message}`
}

function appendLog(msg) {
  logs.value.push({ ts: Date.now() / 1000, message: msg })
  nextTick(() => {
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  })
}

async function submit() {
  const payload = {
    script: form.script,
    command: form.command,
    provider: form.provider,
    force: form.force,
  }
  if (form.limit > 0) payload.limit = form.limit
  try {
    const res = await api.createJob(payload)
    logs.value = []
    activeJob.value = res.job
    if (res.queued_behind) ElMessage.warning(`有任务运行中，已排队（#${res.queued_behind} 之后）`)
    listen(res.job.id)
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

function listen(jobId) {
  if (es) es.close()
  es = new EventSource(`/api/jobs/${jobId}/events`)
  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data)
    handleEvent(data)
  }
  es.onerror = () => {
    // stream ends when job finishes; final state fetched via REST
    if (es) es.close()
    es = null
    refreshJob(jobId)
  }
}

function handleEvent(ev) {
  const job = activeJob.value
  if (!job || ev.job_id !== job.id) return
  if (ev.kind === "snapshot") {
    Object.assign(job, ev.job)
    logs.value = ev.job.logs || []
    return
  }
  if (ev.kind === "log") {
    appendLog(ev.message)
  } else if (ev.kind === "start") {
    job.stage = ev.stage
    job.progress = {}
  } else if (ev.kind === "progress") {
    job.stage = ev.stage
    job.progress = {
      current: ev.current,
      total: ev.total,
      percent: ev.percent,
      id: ev.id,
      cached: ev.cached,
    }
    if (ev.stage === "tts" && ev.cached === false) {
      appendLog(`tts ${ev.id}: ${ev.current}/${ev.total}${ev.cached ? " (cached)" : ""}`)
    }
  } else if (ev.kind === "done") {
    if (ev.stage === "assemble" && ev.total_ms != null) appendLog(`主轨 ${Math.round(ev.total_ms / 1000)}s · ${ev.beds} 垫底层 · 缺失 ${ev.missing}`)
    if (ev.stage === "mix" && ev.duration_ms != null) appendLog(`成品 ${Math.round(ev.duration_ms / 1000)}s`)
  } else if (ev.kind === "job_done") {
    job.status = ev.status || job.status
    if (es) {
      es.close()
      es = null
    }
    ElMessage({
      type: job.status === "done" ? "success" : job.status === "cancelled" ? "warning" : "error",
      message: `任务结束：${job.status}`,
    })
    loadHistory()
  }
}

async function refreshJob(jobId) {
  try {
    const j = await api.getJob(jobId)
    if (activeJob.value && activeJob.value.id === jobId) {
      Object.assign(activeJob.value, j)
      logs.value = j.logs || []
    }
    loadHistory()
  } catch {
    /* job may have been evicted */
  }
}

async function cancel() {
  if (!activeJob.value) return
  try {
    await api.cancelJob(activeJob.value.id)
    ElMessage.info("已发送取消信号")
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

function showHistory(row) {
  if (!row) return
  if (activeJob.value && activeJob.value.status === "running") return
  refreshJob(row.id).then(() => {
    activeJob.value = row
  })
}

async function loadHistory() {
  try {
    const [list, scriptList, voice] = await Promise.all([api.listJobs(), api.listScripts(), api.voiceStatus()])
    history.value = list
    scripts.value = scriptList.map((s) => s.name)
    if (!form.script && scripts.value.length) form.script = scripts.value[0]
    // default engine follows the saved TTS_PROVIDER setting
    if (!providerTouched && voice.provider_default) form.provider = voice.provider_default
    const running = list.find((j) => j.status === "running" || j.status === "queued")
    if (running && !activeJob.value) {
      activeJob.value = running
      logs.value = []
      listen(running.id)
    }
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

onMounted(loadHistory)
onBeforeUnmount(() => {
  if (es) es.close()
})
</script>

<style scoped>
.job-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.stage-row {
  display: flex;
  align-items: center;
}
.log-box {
  max-height: 320px;
  min-height: 120px;
}
</style>
