<template>
  <div class="page">
    <div class="page-title"><el-icon><FolderOpened /></el-icon>素材库</div>

    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="音乐 music/" name="music">
        <AssetTable kind="music" ref="musicTable" />
      </el-tab-pane>
      <el-tab-pane label="音效 sfx/" name="sfx">
        <AssetTable kind="sfx" ref="sfxTable" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import AssetTable from "../components/AssetTable.vue"

const tab = ref("music")
const musicTable = ref(null)
const sfxTable = ref(null)

function load() {
  nextTickRefresh()
}
function nextTickRefresh() {
  const t = tab.value === "music" ? musicTable.value : sfxTable.value
  if (t) t.load()
}

onMounted(() => {
  musicTable.value?.load()
})
</script>
