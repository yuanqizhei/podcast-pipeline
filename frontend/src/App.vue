<template>
  <el-container style="height: 100%">
    <el-aside width="210px" class="aside">
      <div class="brand">
        <el-icon :size="22"><Headset /></el-icon>
        <span>Podcast Studio</span>
      </div>
      <el-menu router :default-active="$route.path" class="menu">
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>仪表盘
        </el-menu-item>
        <el-menu-item index="/scripts">
          <el-icon><EditPen /></el-icon>脚本编辑
        </el-menu-item>
        <el-menu-item index="/build">
          <el-icon><VideoPlay /></el-icon>构建任务
        </el-menu-item>
        <el-menu-item index="/assets">
          <el-icon><FolderOpened /></el-icon>素材库
        </el-menu-item>
        <el-menu-item index="/voice">
          <el-icon><Mic /></el-icon>声音克隆
        </el-menu-item>
        <el-menu-item index="/outputs">
          <el-icon><Headset /></el-icon>产物输出
        </el-menu-item>
      </el-menu>
      <div class="aside-footer mono">podcast-pipeline</div>
    </el-aside>
    <el-main style="padding: 0; overflow: auto">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { useRoute } from "vue-router"
const $route = useRoute()
</script>

<style scoped>
.aside {
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  background: #fff;
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-weight: 700;
  font-size: 16px;
  border-bottom: 1px solid #e4e7ed;
}
.menu {
  border-right: none;
  flex: 1;
}
.aside-footer {
  padding: 12px;
  font-size: 11px;
  color: #909399;
  text-align: center;
  border-top: 1px solid #e4e7ed;
}
</style>
