<template>
  <div class="page" style="max-width: 760px">
    <div class="page-title"><el-icon><Setting /></el-icon>系统设置</div>

    <el-card shadow="never" style="margin-bottom: 16px" v-loading="loading">
      <template #header><span>MiniMax 账号（.env）</span></template>
      <p class="hint">
        密钥保存到项目根目录 <span class="mono">.env</span>，写入后立即生效，无需重启。
        密钥在 MiniMax 开放平台（platform.minimaxi.com）获取。
      </p>
      <el-form label-width="120px" size="default">
        <el-form-item label="API Key">
          <el-input v-model="form.MINIMAX_API_KEY" type="password" show-password
            :placeholder="status.MINIMAX_API_KEY?.set ? `已配置（${status.MINIMAX_API_KEY.masked}），留空保持不变` : '粘贴 MINIMAX_API_KEY'" />
        </el-form-item>
        <el-form-item label="Group ID">
          <el-input v-model="form.MINIMAX_GROUP_ID" type="password" show-password
            :placeholder="status.MINIMAX_GROUP_ID?.set ? `已配置（${status.MINIMAX_GROUP_ID.masked}），留空保持不变` : '粘贴 MINIMAX_GROUP_ID'" />
        </el-form-item>
        <el-form-item label="默认引擎">
          <el-radio-group v-model="form.TTS_PROVIDER">
            <el-radio value="dryrun">dryrun（试跑，不出真声）</el-radio>
            <el-radio value="minimax">minimax（真实合成）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="form.MINIMAX_MODEL" :placeholder="status.MINIMAX_MODEL || '默认 speech-01-turbo'" style="width: 280px" />
          <el-button v-if="status.MINIMAX_MODEL" size="small" text style="margin-left: 6px" @click="resetKey('MINIMAX_MODEL')">
            恢复默认
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span>节目信息（写入成品 MP3 的 ID3 标签）</span></template>
      <el-form label-width="120px">
        <el-form-item label="节目名称">
          <el-input v-model="form.PODCAST_NAME" placeholder="如：终点线一直在挪" style="width: 320px" />
          <el-button v-if="status.PODCAST_NAME" size="small" text style="margin-left: 6px" @click="resetKey('PODCAST_NAME')">
            恢复默认
          </el-button>
        </el-form-item>
        <el-form-item label="作者/主播">
          <el-input v-model="form.PODCAST_ARTIST" placeholder="如：老王" style="width: 320px" />
          <el-button v-if="status.PODCAST_ARTIST" size="small" text style="margin-left: 6px" @click="resetKey('PODCAST_ARTIST')">
            恢复默认
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span>合成参数</span></template>
      <el-form label-width="120px">
        <el-form-item label="语速">
          <el-input-number v-model="form.TTS_SPEED" :min="0.5" :max="2" :step="0.05" />
          <span class="hint" style="margin-left: 10px">0.5 ~ 2.0，越小越慢</span>
          <el-button v-if="status.TTS_SPEED" size="small" text @click="resetKey('TTS_SPEED')">恢复默认</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span>响度规范（loudnorm）</span></template>
      <p class="hint">
        最终混音的两遍 loudnorm 目标。I = 整体响度（播客常用 -16 LUFS，更响可到 -14）；
        TP = 真实峰值上限；LRA = 响度动态范围。默认 I=-16 / TP=-1.5 / LRA=11。
      </p>
      <el-form label-width="120px">
        <el-form-item label="响度 I (LUFS)">
          <el-input-number v-model="form.LOUDNORM_I" :min="-35" :max="-5" :step="0.5" />
          <el-button v-if="status.LOUDNORM_I" size="small" text @click="resetKey('LOUDNORM_I')">恢复默认</el-button>
        </el-form-item>
        <el-form-item label="峰值 TP (dBTP)">
          <el-input-number v-model="form.LOUDNORM_TP" :min="-9" :max="0" :step="0.1" />
          <el-button v-if="status.LOUDNORM_TP" size="small" text @click="resetKey('LOUDNORM_TP')">恢复默认</el-button>
        </el-form-item>
        <el-form-item label="动态 LRA (LU)">
          <el-input-number v-model="form.LOUDNORM_LRA" :min="1" :max="50" :step="1" />
          <el-button v-if="status.LOUDNORM_LRA" size="small" text @click="resetKey('LOUDNORM_LRA')">恢复默认</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="actions">
      <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
      <el-button @click="load">重置</el-button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import api from "../api"

const loading = ref(false)
const saving = ref(false)
const status = ref({})
const form = reactive({
  MINIMAX_API_KEY: "",
  MINIMAX_GROUP_ID: "",
  TTS_PROVIDER: "dryrun",
  MINIMAX_MODEL: "speech-01-turbo",
  TTS_SPEED: 0.95,
  PODCAST_NAME: "",
  PODCAST_ARTIST: "",
  LOUDNORM_I: -16,
  LOUDNORM_TP: -1.5,
  LOUDNORM_LRA: 11,
})

async function load() {
  loading.value = true
  try {
    status.value = await api.getSettings()
    form.MINIMAX_API_KEY = ""
    form.MINIMAX_GROUP_ID = ""
    form.TTS_PROVIDER = status.value.TTS_PROVIDER || "dryrun"
    form.MINIMAX_MODEL = status.value.MINIMAX_MODEL || ""
    form.TTS_SPEED = parseFloat(status.value.TTS_SPEED) || 0.95
    form.PODCAST_NAME = status.value.PODCAST_NAME || ""
    form.PODCAST_ARTIST = status.value.PODCAST_ARTIST || ""
    form.LOUDNORM_I = parseFloat(status.value.LOUDNORM_I) || -16
    form.LOUDNORM_TP = status.value.LOUDNORM_TP ? parseFloat(status.value.LOUDNORM_TP) : -1.5
    form.LOUDNORM_LRA = parseFloat(status.value.LOUDNORM_LRA) || 11
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    loading.value = false
  }
}

const DEFAULTS = {
  MINIMAX_MODEL: "",
  TTS_SPEED: 0.95,
  PODCAST_NAME: "",
  PODCAST_ARTIST: "",
  LOUDNORM_I: -16,
  LOUDNORM_TP: -1.5,
  LOUDNORM_LRA: 11,
}

async function resetKey(key) {
  try {
    await api.saveSettings({ [key]: null })
    status.value = await api.getSettings()
    if (key in DEFAULTS) form[key] = DEFAULTS[key]
    ElMessage.success(`${key} 已恢复默认`)
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function save() {
  saving.value = true
  try {
    const payload = {
      TTS_PROVIDER: form.TTS_PROVIDER,
      TTS_SPEED: String(form.TTS_SPEED),
      LOUDNORM_I: String(form.LOUDNORM_I),
      LOUDNORM_TP: String(form.LOUDNORM_TP),
      LOUDNORM_LRA: String(form.LOUDNORM_LRA),
    }
    if (form.MINIMAX_MODEL.trim()) payload.MINIMAX_MODEL = form.MINIMAX_MODEL.trim()
    if (form.MINIMAX_API_KEY.trim()) payload.MINIMAX_API_KEY = form.MINIMAX_API_KEY.trim()
    if (form.MINIMAX_GROUP_ID.trim()) payload.MINIMAX_GROUP_ID = form.MINIMAX_GROUP_ID.trim()
    if (form.PODCAST_NAME.trim()) payload.PODCAST_NAME = form.PODCAST_NAME.trim()
    if (form.PODCAST_ARTIST.trim()) payload.PODCAST_ARTIST = form.PODCAST_ARTIST.trim()
    const res = await api.saveSettings(payload)
    ElMessage.success(`已保存：${res.saved.join(", ")}`)
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.7;
}
.actions {
  display: flex;
  gap: 10px;
}
</style>
