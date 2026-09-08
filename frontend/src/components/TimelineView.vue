<template>
  <div class="tl-view">
    <div class="tl-head">
      <el-tag type="info" effect="plain">{{ tl.speech_blocks }} 语音块</el-tag>
      <el-tag type="info" effect="plain">{{ tl.chars }} 字</el-tag>
      <el-tag type="info" effect="plain">约 {{ estTotal }} 分钟</el-tag>
      <el-tag v-if="tl.missing_assets.length" type="danger" effect="plain">
        {{ new Set(tl.missing_assets).size }} 素材缺失
      </el-tag>
    </div>
    <el-scrollbar class="tl-scroll">
      <div v-for="(item, i) in tl.items" :key="i" class="tl-item" :class="item.type">
        <span class="tl-badge">
          <template v-if="item.type === 'speech'"><el-icon><ChatDotRound /></el-icon></template>
          <template v-else-if="item.type === 'pause'"><el-icon><Timer /></el-icon></template>
          <template v-else-if="item.type === 'insert'"><el-icon><Bell /></el-icon></template>
          <template v-else-if="item.type === 'bed'"><el-icon><Headset /></el-icon></template>
          <template v-else><el-icon><SwitchButton /></el-icon></template>
        </span>
        <div class="tl-body">
          <template v-if="item.type === 'speech'">
            <div class="tl-title mono">{{ item.id }} · ~{{ estSec(item.text) }}s</div>
            <div class="tl-text">{{ preview(item.text) }}</div>
          </template>
          <template v-else-if="item.type === 'pause'">
            <div class="tl-title">停顿 {{ item.seconds }}s</div>
          </template>
          <template v-else-if="item.type === 'insert'">
            <div class="tl-title">
              插入播放 · <span class="mono">{{ item.file }}</span>
              <span v-if="!item.exists" class="missing">（缺失）</span>
              <span v-else class="ok">（就绪）</span>
            </div>
            <div class="tl-sub">gain {{ item.gain_db }}dB · fade {{ item.fade_in }}/{{ item.fade_out }}s</div>
          </template>
          <template v-else-if="item.type === 'bed'">
            <div class="tl-title">
              垫底循环 · <span class="mono">{{ item.file }}</span>
              <span v-if="!item.exists" class="missing">（缺失）</span>
              <span v-else class="ok">（就绪）</span>
            </div>
            <div class="tl-sub">gain {{ item.gain_db }}dB · fade {{ item.fade_in }}/{{ item.fade_out }}s</div>
          </template>
          <template v-else>
            <div class="tl-title">结束垫底</div>
          </template>
        </div>
      </div>
      <el-empty v-if="!tl.items.length" description="空时间轴" :image-size="60" />
    </el-scrollbar>
  </div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({ timeline: { type: Object, required: true } })
const tl = computed(() => props.timeline)

function estSec(text) {
  return Math.max(1, Math.round(text.length / 4.5))
}
const estTotal = computed(() => {
  let sec = 0
  for (const it of tl.value.items) {
    if (it.type === "speech") sec += it.text.length / 4.5
    else if (it.type === "pause") sec += it.seconds
    else if (it.type === "insert" || it.type === "bed") sec += it.fade_in + it.fade_out + 1
  }
  return Math.max(1, Math.round(sec / 60))
})
function preview(text) {
  const one = text.replace(/\n/g, " ")
  return one.length > 80 ? one.slice(0, 80) + "…" : one
}
</script>

<style scoped>
.tl-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.tl-head {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #ebeef5;
  flex-wrap: wrap;
}
.tl-scroll {
  flex: 1;
}
.tl-item {
  display: flex;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px dashed #f0f0f0;
  align-items: flex-start;
}
.tl-badge {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
  background: #909399;
  margin-top: 2px;
}
.tl-item.speech .tl-badge {
  background: #409eff;
}
.tl-item.pause .tl-badge {
  background: #c0c4cc;
}
.tl-item.insert .tl-badge {
  background: #9a6fe0;
}
.tl-item.bed .tl-badge {
  background: #67c23a;
}
.tl-item.bed_stop .tl-badge {
  background: #b3e19d;
  color: #333;
}
.tl-body {
  flex: 1;
  min-width: 0;
}
.tl-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.tl-sub {
  font-size: 12px;
  color: #909399;
}
.tl-text {
  font-size: 12.5px;
  color: #606266;
  margin-top: 2px;
  line-height: 1.5;
}
.missing {
  color: #f56c6c;
}
.ok {
  color: #67c23a;
}
</style>
