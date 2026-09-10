<template>
  <div class="page" style="max-width: 760px">
    <div class="page-title"><el-icon><Mic /></el-icon>声音克隆</div>

    <el-card shadow="never" style="margin-bottom: 16px" v-loading="loading">
      <template #header><span>当前配置（.env）</span></template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="默认引擎">
          <el-tag size="small" :type="status.provider_default === 'minimax' ? 'success' : 'info'">
            {{ status.provider_default }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型">{{ status.model }}</el-descriptions-item>
        <el-descriptions-item label="API Key">
          <el-tag size="small" :type="status.api_key_set ? 'success' : 'danger'">
            {{ status.api_key_set ? "已配置" : "未配置" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Group ID">
          <el-tag size="small" :type="status.group_id_set ? 'success' : 'danger'">
            {{ status.group_id_set ? "已配置" : "未配置" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="克隆声音" :span="2">
          <div class="voice-id-row">
            <span v-if="status.voice_id" class="mono ok">{{ status.voice_id }}</span>
            <el-tag v-else size="small" type="warning">尚未克隆</el-tag>
            <el-input v-model="manualVoiceId" size="small" placeholder="手动粘贴 voice_id"
              style="width: 240px; margin-left: 8px" />
            <el-button size="small" :disabled="!manualVoiceId.trim()" @click="setVoiceId">设为此 ID</el-button>
            <el-popconfirm v-if="status.voice_id" title="清除 voice_id？将回到平台默认音色" @confirm="setVoiceId(null)">
              <template #reference>
                <el-button size="small" type="warning" plain>清除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="语速" :span="2">
          <el-input-number v-model="speed" :min="0.5" :max="2" :step="0.05" size="small" />
          <el-button size="small" style="margin-left: 8px" @click="saveSpeed">保存语速</el-button>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="!status.api_key_set || !status.group_id_set"
        type="info"
        show-icon :closable="false" style="margin-top: 12px"
      >
        <template #title>
          尚未配置 MiniMax 密钥，请前往
          <router-link to="/settings">系统设置</router-link>
          填写 MINIMAX_API_KEY 与 MINIMAX_GROUP_ID
        </template>
      </el-alert>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span>浏览器直接录音</span></template>
      <p class="hint">
        点击开始后朗读 <b>1 分钟以上</b>（安静环境、自然语速）。录音先在本机试听，满意后点"克隆此录音"，
        后端会自动转成 wav 再上传 MiniMax。
      </p>
      <div class="rec-row">
        <el-button v-if="!recording" type="primary" :icon="Mic" :disabled="!!recordedUrl" @click="startRec">
          开始录音
        </el-button>
        <el-button v-else type="danger" :icon="VideoPause" @click="stopRec">
          停止（{{ recSeconds }}s{{ recSeconds < 60 ? "，建议 60s+" : "" }}）
        </el-button>
        <span v-if="recording" class="rec-dot"></span>
        <el-button v-if="recordedUrl" text @click="resetRec">丢弃重录</el-button>
      </div>
      <div v-if="recordedUrl" class="rec-preview">
        <span class="mono">{{ recordedName }}（{{ recSeconds }}s）</span>
        <audio :src="recordedUrl" controls style="width: 100%"></audio>
        <el-button type="primary" :loading="cloning" style="margin-top: 8px" @click="cloneRecording">
          克隆此录音
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header><span>上传声音样本</span></template>
      <p class="hint">
        也可以上传已录好的样本文件（wav/mp3/m4a/webm）。上传后 MiniMax 返回 voice_id 并自动写入 .env，
        之后所有合成均使用你的克隆声音。
      </p>
      <el-upload drag :show-file-list="false" :http-request="doClone" accept=".wav,.mp3,.m4a,.webm,.ogg,.mp4" :disabled="cloning">
        <el-icon :size="40" style="color: #909399"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽样本到此处，或 <em>点击选择</em></div>
      </el-upload>
      <el-progress v-if="cloning" :indeterminate="true" :show-percentage="false" style="margin-top: 12px" />
    </el-card>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { Mic, VideoPause } from "@element-plus/icons-vue"
import api from "../api"

const status = ref({})
const speed = ref(0.95)
const loading = ref(false)
const cloning = ref(false)
const manualVoiceId = ref("")

async function setVoiceId(value) {
  const payload = value === null ? { MINIMAX_VOICE_ID: null } : { MINIMAX_VOICE_ID: manualVoiceId.value.trim() }
  try {
    await api.saveSettings(payload)
    ElMessage.success(value === null ? "已清除 voice_id" : "voice_id 已保存")
    manualVoiceId.value = ""
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

const recording = ref(false)
const recSeconds = ref(0)
const recordedUrl = ref("")
const recordedBlob = ref(null)
const recordedName = ref("")
let recorder = null
let timer = null
let stream = null

function pickMime() {
  const cands = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
  for (const m of cands) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m
  }
  return ""
}

async function startRec() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    ElMessage.error("无法访问麦克风，请检查浏览器权限")
    return
  }
  const mime = pickMime()
  recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  const chunks = []
  recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data)
  recorder.onstop = () => {
    recordedBlob.value = new Blob(chunks, { type: recorder.mimeType || "audio/webm" })
    recordedUrl.value = URL.createObjectURL(recordedBlob.value)
    recordedName.value = (recorder.mimeType || "").includes("mp4") ? "recorded.mp4" : "recorded.webm"
  }
  recorder.start()
  recording.value = true
  recSeconds.value = 0
  timer = setInterval(() => (recSeconds.value += 1), 1000)
}

function stopRec() {
  recorder?.stop()
  stream?.getTracks().forEach((t) => t.stop())
  clearInterval(timer)
  recording.value = false
}

function resetRec() {
  if (recordedUrl.value) URL.revokeObjectURL(recordedUrl.value)
  recordedUrl.value = ""
  recordedBlob.value = null
  recSeconds.value = 0
}

async function cloneRecording() {
  if (!recordedBlob.value) return
  cloning.value = true
  try {
    const res = await api.cloneVoice(new File([recordedBlob.value], recordedName.value, { type: recordedBlob.value.type }))
    ElMessage.success(`克隆成功：${res.voice_id}`)
    resetRec()
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    cloning.value = false
  }
}

onBeforeUnmount(() => {
  if (recording.value) stopRec()
  resetRec()
})

async function load() {
  loading.value = true
  try {
    status.value = await api.voiceStatus()
    speed.value = parseFloat(status.value.speed) || 0.95
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    loading.value = false
  }
}

async function doClone(opt) {
  cloning.value = true
  try {
    const res = await api.cloneVoice(opt.file)
    ElMessage.success(`克隆成功：${res.voice_id}`)
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    cloning.value = false
  }
}

async function saveSpeed() {
  try {
    await api.setSpeed(speed.value)
    ElMessage.success("语速已保存")
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

onMounted(load)
</script>

<style scoped>
.hint {
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
  margin-bottom: 12px;
}
.ok {
  color: #67c23a;
}
.voice-id-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.rec-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.rec-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f56c6c;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% {
    opacity: 0.2;
  }
}
.rec-preview {
  margin-top: 12px;
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rec-preview span {
  font-size: 12px;
  color: #606266;
}
</style>
