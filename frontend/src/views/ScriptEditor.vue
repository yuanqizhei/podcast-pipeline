<template>
  <div class="page editor-page">
    <div class="toolbar">
      <el-select v-model="current" style="width: 220px" placeholder="选择脚本" @change="switchTo">
        <el-option v-for="s in scriptNames" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button :icon="Refresh" @click="loadNames" title="刷新列表" circle />
      <div class="spacer" />
      <el-tag v-if="dirty" type="warning" size="small">未保存</el-tag>
      <el-tag v-else-if="loaded" type="success" size="small">已保存</el-tag>
      <el-button type="primary" :icon="DocumentChecked" :disabled="!loaded" :loading="saving" @click="save">
        保存并解析 (Ctrl+S)
      </el-button>
    </div>

    <el-alert v-if="parseError" type="error" show-icon :closable="false" style="margin-bottom: 10px"
      :title="parseError" />

    <div class="split">
      <div class="pane">
        <div ref="cmHost" class="cm-host"></div>
      </div>
      <div class="pane">
        <TimelineView v-if="timeline" :timeline="timeline" />
        <el-empty v-else description="保存后此处显示时间轴预览" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { DocumentChecked, Refresh } from "@element-plus/icons-vue"
import { EditorView, keymap, lineNumbers, highlightActiveLine } from "@codemirror/view"
import { EditorState } from "@codemirror/state"
import { StreamLanguage, syntaxHighlighting, defaultHighlightStyle } from "@codemirror/language"
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands"
import api from "../api"
import TimelineView from "../components/TimelineView.vue"

const route = useRoute()
const router = useRouter()

const scriptNames = ref([])
const current = ref(route.params.name || "")
const loaded = ref(false)
const dirty = ref(false)
const saving = ref(false)
const timeline = ref(null)
const parseError = ref("")
const cmHost = ref(null)

let view = null

const podcastLang = StreamLanguage.define({
  token(stream) {
    if (stream.eatSpace()) return null
    if (stream.match(/^#[^\n]*/)) return "comment"
    if (stream.match(/^@[\w]+/)) return "keyword"
    if (stream.match(/^(gain|fade_in|fade_out)=/)) return "propertyName"
    if (stream.match(/^=?[-\w./]+/)) return "string"
    stream.next()
    return null
  },
})

function createEditor(content) {
  if (view) view.destroy()
  const state = EditorState.create({
    doc: content,
    extensions: [
      lineNumbers(),
      highlightActiveLine(),
      history(),
      keymap.of([
        {
          key: "Mod-s",
          preventDefault: true,
          run: () => {
            save()
            return true
          },
        },
        ...defaultKeymap,
        ...historyKeymap,
        indentWithTab,
      ]),
      podcastLang,
      syntaxHighlighting(defaultHighlightStyle),
      EditorView.lineWrapping,
      EditorView.updateListener.of((u) => {
        if (u.docChanged) dirty.value = true
      }),
    ],
  })
  view = new EditorView({ state, parent: cmHost.value })
}

async function loadNames() {
  const list = await api.listScripts()
  scriptNames.value = list.map((s) => s.name)
  if (!current.value && scriptNames.value.length) {
    current.value = scriptNames.value[0]
  }
}

async function switchTo(name) {
  if (name) router.replace(`/scripts/${name}`)
  await load(name)
}

async function load(name) {
  if (!name) return
  try {
    const data = await api.getScript(name)
    loaded.value = true
    parseError.value = data.parse_error || ""
    timeline.value = data.timeline
    dirty.value = false
    await nextTick()
    createEditor(data.content)
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
}

async function save() {
  if (!loaded.value || !view) return
  saving.value = true
  try {
    const res = await api.saveScript(current.value, view.state.doc.toString())
    timeline.value = res.timeline
    parseError.value = res.parse_error || ""
    dirty.value = false
    ElMessage.success("已保存")
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadNames()
  if (current.value) await load(current.value)
})

onBeforeUnmount(() => {
  if (view) view.destroy()
})

watch(
  () => route.params.name,
  (n) => {
    if (n && n !== current.value) {
      current.value = n
      load(n)
    }
  }
)
</script>

<style scoped>
.editor-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.spacer {
  flex: 1;
}
.split {
  flex: 1;
  display: flex;
  gap: 12px;
  min-height: 0;
}
.pane {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.cm-host {
  flex: 1;
  overflow: hidden;
}
.pane :deep(.el-empty),
.pane :deep(.el-scrollbar) {
  flex: 1;
}
</style>
