<template>
  <div class="page editor-page">
    <div class="toolbar">
      <el-select v-model="current" style="width: 220px" placeholder="选择脚本" @change="switchTo">
        <el-option v-for="s in scriptNames" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button :icon="Refresh" @click="loadNames" title="刷新列表" circle />
      <el-button :icon="Plus" @click="createNew">新建脚本</el-button>
      <el-button :icon="EditPen" :disabled="!loaded" @click="renameCurrent">重命名</el-button>
      <el-upload :show-file-list="false" :before-upload="importTxt" accept=".txt" title="导入 txt 文件">
        <el-button :icon="Upload" title="导入 txt 文件">导入</el-button>
      </el-upload>
      <div class="spacer" />
      <el-button :icon="QuestionFilled" @click="helpVisible = true">语法帮助</el-button>
      <el-tag v-if="dirty" type="warning" size="small">未保存</el-tag>
      <el-tag v-else-if="loaded" type="success" size="small">已保存</el-tag>
      <el-button type="primary" :icon="DocumentChecked" :disabled="!loaded" :loading="saving" @click="save">
        保存并解析 (Ctrl+S)
      </el-button>
    </div>

    <el-alert v-if="parseError" type="error" show-icon :closable="false" style="margin-bottom: 10px"
      :title="parseError" />

    <el-drawer v-model="helpVisible" title="脚本语法参考" size="420px">
      <div class="help-body">
        <p class="hint">纯文本即口播稿；连续的非空行合成为一段语音。以下指令独占一行：</p>
        <div v-for="d in directives" :key="d.name" class="help-item">
          <div class="help-head">
            <span class="mono kw">{{ d.name }}</span>
            <span class="desc">{{ d.desc }}</span>
            <el-button size="small" text type="primary" @click="insertTemplate(d.tpl)">插入</el-button>
          </div>
          <pre class="mono tpl">{{ d.tpl }}</pre>
        </div>
        <p class="hint" style="margin-top: 10px">
          <code>#</code> 开头为注释；<code>#%%</code> 可作分段标题；音频文件放
          <code>audio/music/</code> 或 <code>audio/sfx/</code>（素材库可复制引用路径）；
          缺失素材自动跳过并警告。
        </p>
      </div>
    </el-drawer>

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
import { DocumentChecked, EditPen, Plus, QuestionFilled, Refresh, Upload } from "@element-plus/icons-vue"
import { ElMessageBox } from "element-plus"
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
const helpVisible = ref(false)

const directives = [
  { name: "@pause", desc: "静默停顿（秒）", tpl: "@pause 2" },
  { name: "@insert", desc: "插入一段音频（点缀音效）", tpl: "@insert sfx/ding.mp3 gain=-10 fade_in=0.5 fade_out=0.5" },
  { name: "@bed", desc: "开始背景乐（循环垫底，人声自动闪避）", tpl: "@bed music/bgm_soft.mp3 gain=-20 fade_in=3 fade_out=3" },
  { name: "@bed_stop", desc: "结束背景乐", tpl: "@bed_stop" },
]

function insertTemplate(tpl) {
  if (!view) return
  const pos = view.state.selection.main.head
  view.dispatch({ changes: { from: pos, insert: tpl + "\n" }, selection: { anchor: pos + tpl.length + 1 } })
  dirty.value = true
  helpVisible.value = false
}

async function renameCurrent() {
  if (!current.value) return
  try {
    const { value } = await ElMessageBox.prompt("新脚本名", "重命名", {
      inputValue: current.value,
      inputPattern: /^[A-Za-z0-9_-]+$/,
      inputErrorMessage: "名称只能包含字母、数字、- 和 _",
    })
    const newName = value.trim()
    if (!newName || newName === current.value) return
    const res = await api.renameScript(current.value, newName)
    await loadNames()
    current.value = newName
    router.replace(`/scripts/${newName}`)
    await load(newName)
    ElMessage.success(`已重命名（缓存已跟随：${res.segments_moved ? "是" : "无缓存"}）`)
  } catch (e) {
    if (e !== "cancel" && e?.message !== "cancel") ElMessage.error(api.errMsg(e))
  }
}

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

async function createNew() {
  try {
    const { value } = await ElMessageBox.prompt("脚本名（字母/数字/中划线/下划线）", "新建脚本", {
      inputValue: "",
      inputPattern: /^[A-Za-z0-9_-]+$/,
      inputErrorMessage: "名称只能包含字母、数字、- 和 _",
    })
    const name = value.trim()
    if (!name) return
    const template = `# ${name}\n\n`
    await api.createScript(name, template)
    await loadNames()
    current.value = name
    router.replace(`/scripts/${name}`)
    await load(name)
    ElMessage.success(`已创建脚本：${name}`)
  } catch (e) {
    if (e !== "cancel" && e?.message !== "cancel") ElMessage.error(api.errMsg(e))
  }
}

async function importTxt(file) {
  const text = await file.text()
  const name = file.name.replace(/\.txt$/i, "")
  try {
    if (loaded.value && view) {
      // replace content of the currently open script
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } })
      dirty.value = true
      ElMessage.success(`已导入 ${file.name}（${text.length} 字符），记得保存`)
    } else if (name) {
      // no script open yet -> create a new one named after the file
      await api.createScript(name, text)
      await loadNames()
      current.value = name
      router.replace(`/scripts/${name}`)
      await load(name)
      ElMessage.success(`已导入并创建脚本：${name}`)
    }
  } catch (e) {
    ElMessage.error(api.errMsg(e))
  }
  return false // prevent el-upload from auto-uploading
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
.help-body {
  padding: 0 4px;
}
.hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.8;
}
.help-item {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 10px;
}
.help-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.help-head .kw {
  color: #409eff;
  font-weight: 600;
}
.help-head .desc {
  flex: 1;
  color: #606266;
  font-size: 12px;
}
.tpl {
  margin: 6px 0 0;
  padding: 6px 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
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
