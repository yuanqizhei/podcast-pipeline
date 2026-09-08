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
          <span v-if="status.voice_id" class="mono ok">{{ status.voice_id }}</span>
          <el-tag v-else size="small" type="warning">尚未克隆</el-tag>
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
        title="在项目根目录 .env 中填写 MINIMAX_API_KEY 与 MINIMAX_GROUP_ID（MiniMax 开放平台获取）"
      />
    </el-card>

    <el-card shadow="never">
      <template #header><span>上传声音样本</span></template>
      <p class="hint">
        安静环境录制 <b>1 分钟以上</b>自然语速朗读（wav/mp3/m4a）。上传后 MiniMax 返回 voice_id 并自动写入 .env，
        之后所有合成均使用你的克隆声音。
      </p>
      <el-upload drag :show-file-list="false" :http-request="doClone" accept=".wav,.mp3,.m4a" :disabled="cloning">
        <el-icon :size="40" style="color: #909399"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽样本到此处，或 <em>点击选择</em></div>
      </el-upload>
      <el-progress v-if="cloning" :indeterminate="true" :show-percentage="false" style="margin-top: 12px" />
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import api from "../api"

const status = ref({})
const speed = ref(0.95)
const loading = ref(false)
const cloning = ref(false)

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
</style>
