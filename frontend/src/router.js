import { createRouter, createWebHistory } from "vue-router"

const routes = [
  { path: "/", name: "dashboard", component: () => import("./views/Dashboard.vue") },
  { path: "/scripts/:name?", name: "editor", component: () => import("./views/ScriptEditor.vue") },
  { path: "/build", name: "build", component: () => import("./views/BuildPanel.vue") },
  { path: "/assets", name: "assets", component: () => import("./views/Assets.vue") },
  { path: "/voice", name: "voice", component: () => import("./views/VoiceClone.vue") },
  { path: "/outputs", name: "outputs", component: () => import("./views/Outputs.vue") },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
