import axios from "axios"

const http = axios.create({ baseURL: "/api", timeout: 120000 })

function errMsg(e) {
  return e?.response?.data?.error || e.message || String(e)
}

export const api = {
  errMsg,
  // scripts
  listScripts: () => http.get("/scripts").then((r) => r.data),
  getScript: (name) => http.get(`/scripts/${name}`).then((r) => r.data),
  createScript: (name, content) => http.post("/scripts", { name, content }).then((r) => r.data),
  saveScript: (name, content) => http.put(`/scripts/${name}`, { content }).then((r) => r.data),
  deleteScript: (name, withSegments) =>
    http.delete(`/scripts/${name}${withSegments ? "?with_segments=1" : ""}`).then((r) => r.data),
  parseScript: (name) => http.post(`/scripts/${name}/parse`).then((r) => r.data),
  // jobs
  listJobs: () => http.get("/jobs").then((r) => r.data),
  getJob: (id) => http.get(`/jobs/${id}`).then((r) => r.data),
  createJob: (payload) => http.post("/jobs", payload).then((r) => r.data),
  cancelJob: (id) => http.post(`/jobs/${id}/cancel`).then((r) => r.data),
  // assets
  listAssets: (kind) => http.get(`/assets/${kind}`).then((r) => r.data),
  deleteAsset: (kind, name) => http.delete(`/assets/${kind}/${name}`).then((r) => r.data),
  // voice / env
  voiceStatus: () => http.get("/voice").then((r) => r.data),
  cloneVoice: (file) => {
    const fd = new FormData()
    fd.append("file", file)
    return http.post("/voice/clone", fd, { timeout: 360000 }).then((r) => r.data)
  },
  setSpeed: (speed) => http.post("/voice/speed", { speed }).then((r) => r.data),
  envInfo: () => http.get("/env").then((r) => r.data),
  // outputs / segments
  listOutputs: () => http.get("/outputs").then((r) => r.data),
  listSegments: (name) => http.get(`/episodes/${name}/segments`).then((r) => r.data),
  deleteSegment: (name, id) => http.delete(`/episodes/${name}/segments/${id}`).then((r) => r.data),
  clearSegments: (name) => http.delete(`/episodes/${name}/segments`).then((r) => r.data),
}

export default api
