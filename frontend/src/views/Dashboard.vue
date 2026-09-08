<template>
  <div class="page">
    <div class="page-title">
      <el-icon><Odometer /></el-icon>仪表盘
      <el-button style="margin-left: auto" type="primary" :icon="Plus" @click="newDlg = true">新建脚本</el-button>
    </div>

    <el-alert v-if="envErrors.length" type="warning" show-icon :closable="false" style="margin-bottom: 16px"
      :title="'MiniMax 尚未配置：' + envErrors.join('；') + '（可先使用 dryrun 模式）'" />

    <el-row :gutter="16">
      <el-col v-for="s in scripts" :key="s.name" :xs="24" :sm="12" :md="8" :lg="6" style="margin-bottom: 16px">
        <el-card shadow="hover" class="ep-card">
          <template #header>
            <div class="card-head">
              <span class="ep-name mono">{{ s.name }}</span>
              <el-tag v-if="s.has_final" type="success" size="small">已出片</el-tag>
            </div>
          </template>
          <div class="stat-row" v-if="!s.parse_error">
            <div class="stat"><b>{{ s.speech_blocks }}</b><span>语音块</span></div>
            <div class="stat"><b>{{ s.chars }}</b><span>字数</span></div>
            <div class="stat"><b>{{ s.segment_count }}</b><span>缓存段</span></div>
            <div class="stat"><b>~{{ estMinutes(s.chars) }}</b><span>分钟</span></div>
          </div>
          <div v-else>
            <el-alert type="error" :closable="false" show-icon :title="s.parse_error" />
          </div>
          <div style="margin-top: 10px; min-height: 20px">
            <el-tooltip v-if="s.missing_assets && s.missing_assets.length" placement="top">
              <template #content>
                缺失素材：<br />{{ [...new Set(s.missing_assets)].join('<br/>') }}
              </template>
              <el-tag type="danger" size="small" effect="plain">
                <el-icon><Warning /></el-icon>
                {{ new Set(s.missing_assets).size }} 个缺失素材
              </el-tag>
            </el-tooltip>
          </div>
          <div class="card-actions">
            <el-button size="small" :icon="EditPen" @click="$router.push(`/scripts/${s.name}`)">编辑</el-button>
            <el-button size="small" type="primary" :icon="VideoPlay"
              @click="$router.push({ path: '/build', query: { script: s.name } })">构建</el-button>
            <el-popconfirm title="删除该脚本？" width="230" :hide-after="0"
              @confirm="remove(s, false)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete" plain>删除</el-button>
              </template>
            </el-popconfirm>
            <el-popconfirm v-if="s.segment_count > 0" title="同时清空该集语音缓存？" width="230"
              confirm-button-text="连缓存删" cancel-button-text="仅删脚本" :hide-after="0"
              @confirm="remove(s, true)">
              <template #reference>
                <el-button size="small" type="danger" :icon="Delete" text title="删除脚本并清空缓存">连缓存</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-if="!scripts.length && !loading" description="还没有脚本，点右上角新建" />

    <el-dialog v-model="newDlg" title="新建口播稿" width="520">
      <el-form label-width="70px">
        <el-form-item label="名称">
          <el-input v-model="newName" placeholder="episode02（仅字母数字-_）" />
        </el-form-item>
      </el-form>
      <p class="hint">将以模板创建：含 @pause / @insert / @bed 指令示例，可参考 episode01。</p>
      <template #footer>
        <el-button @click="newDlg = false">取消</el-button>
        <el-button type="primary" :disabled="!newName" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { Plus, EditPen, VideoPlay, Delete, Warning } from "@element-plus/icons-vue"
import api from "../api"

const TEMPLATE = `#%% 开场

@bed music/bgm_intro.mp3 gain=-24 fade_in=4 fade_out=3

在这里写下你的开场白。

@bed_stop

@pause 1

#%% 正文

正文内容……

@pause 2

#%% 结尾

@insert music/bgm_warm.mp3 gain=-14 fade_in=1 fade_out=4
`

const loading = ref(false)
const scripts = ref([])
const envErrors = ref([])
const newDlg = ref(false)
const newName = ref("")

function estMinutes(chars) {
  return Math.round(chars / 4.5 / 60)
}

async function load() {
  loading.value = true
  try {
    scripts.value = await api.listScripts()
    const env = await api.envInfo()
    envErrors.value = env.minimax_preflight_errors
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    loading.value = false
  }
}

async function create() {
  try {
    await api.createScript(newName.value.trim(), TEMPLATE)
    ElMessage.success("已创建")
    newDlg.value = false
    newName.value = ""
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function remove(s, withSegments) {
  try {
    await api.deleteScript(s.name, withSegments)
    ElMessage.success("已删除")
    load()
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

onMounted(load)
</script>

<style scoped>
.ep-card :deep(.el-card__body) {
  padding: 14px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ep-name {
  font-weight: 700;
}
.stat-row {
  display: flex;
  gap: 4px;
}
.stat {
  flex: 1;
  text-align: center;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 6px 2px;
}
.stat b {
  display: block;
  font-size: 16px;
  color: #409eff;
}
.stat span {
  font-size: 11px;
  color: #909399;
}
.card-actions {
  margin-top: 12px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.hint {
  color: #909399;
  font-size: 12px;
}
</style>
