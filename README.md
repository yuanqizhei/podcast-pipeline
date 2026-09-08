# podcast-pipeline

一条命令，把文字口播稿变成一期完整的播客节目。

基于 AI 语音合成（你自己的克隆声音）+ 自动混音（背景音乐、环境音效、BGM 闪避、响度归一）的全自动播客生产流水线。首期节目《终点线一直在挪》——一期关于"人生终点"的人生感悟类独白播客。

**CLI 与 Web Studio 双形态**：除命令行外，内置本地 Web 控制台（Flask + Vue 3），脚本编辑、发起构建、实时日志、素材管理、声音克隆全部图形化操作。

```
script/episode01.txt  ──►  你克隆的声音朗读  ──►  自动混入音乐音效  ──►  episode01_final.mp3
     （口播稿）              （MiniMax TTS）         （ffmpeg 闪避混音）        （-16 LUFS，可直接发布）
```

## 功能特性

- **声音克隆**：录 1 分钟样本，之后所有节目都用你的声音朗读
- **标注语法**：在口播稿里用 `@pause` / `@insert` / `@bed` 指令控制停顿、插入音效、垫底音乐，与写作流程融为一体
- **专业混音**：说话时自动压低背景音（sidechain 闪避）、双遍响度测量精确归一到 -16 LUFS 播客标准、防削波限幅
- **智能缓存**：语音段按内容 hash 缓存且按集隔离——改稿只重新合成变化的段落，多集生产互不干扰
- **试听模式**：`--limit 3` 先出 30 秒小样验证音色语速，满意再跑全片
- **容错设计**：音乐/音效素材缺失不阻塞出片（警告跳过）；脚本指令错误带行号提示；兼容 Windows 记事本的 UTF-8 BOM
- **零成本验证**：`dryrun` 模式用静音替代真实合成，不花一分钱跑通全流程
- **Web Studio**：本地可视化控制台——语法高亮脚本编辑器、时间轴预览、一键构建、SSE 实时进度日志、素材库、语音缓存管理

## 环境要求

- Python 3.10+（3.13 需额外装 `audioop-lts`，已含在 requirements.txt）
- ffmpeg + ffprobe（须在 PATH，或位于 `~/miniconda3` 等常见位置——脚本会自动探测）
- [MiniMax 开放平台](https://platform.minimaxi.com)账号（真实合成时）
- Node.js 18+（仅 Web Studio：构建前端 / 开发模式）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

Windows 下安装 ffmpeg（任选其一）：

```bash
# 方式一：conda（国内推荐清华镜像）
conda install -y --override-channels -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/ ffmpeg

# 方式二：winget
winget install Gyan.FFmpeg
```

### 2. 配置密钥

```bash
copy .env.example .env   # Windows；Linux/macOS 用 cp
```

在 `.env` 中填入 `MINIMAX_API_KEY` 和 `MINIMAX_GROUP_ID`（MiniMax 平台获取）。

### 3. 克隆你的声音

安静环境录制 **1 分钟以上**的自然语速朗读（wav 格式），然后：

```bash
python -m src.cli clone 你的样本.wav
```

成功后 `MINIMAX_VOICE_ID` 自动写入 `.env`，以后无需重复操作。

### 4. 准备音频素材（可选，缺失不阻塞）

放入 `audio/` 目录，文件名与脚本标注对应：

| 文件 | 用途 | 获取建议 |
|------|------|----------|
| `music/bgm_intro.mp3` | 片头曲 | Suno 生成（prompt：lo-fi, warm, nostalgic, podcast intro） |
| `music/bgm_transition.mp3` | 幕间转场 | 同上 |
| `music/bgm_warm.mp3` | 尾声垫底乐 | 同上 |
| `sfx/street_night.mp3` | 夜晚街道环境音 | 剪映音效库 / freesound.org |
| `sfx/glasses_clink.mp3` | 碰杯声 | 同上 |
| `sfx/footsteps.mp3` | 脚步声 | 同上 |

### 5. 出片

```bash
# 先试听：只合成前 3 个语音块（约 30 秒）
python -m src.cli build script/episode01.txt --provider minimax --limit 3

# 满意后全片
python -m src.cli build script/episode01.txt --provider minimax

# 或先用零成本模式验证脚本结构
python -m src.cli build script/episode01.txt --provider dryrun
```

成品输出：`audio/output/episode01_final.mp3`（44.1kHz / 128kbps / -16 LUFS），可直接上传小宇宙、喜马拉雅、Apple Podcasts。

## Web Studio（本地控制台）

图形化完成全部生产流程，无需记命令。

### 启动

```bash
# 首次使用需构建前端（需 Node.js 18+）
cd frontend
npm install
npm run build
cd ..

# 一键启动（自动托管前端构建产物）
python run.py          # → http://127.0.0.1:5000
```

前端开发模式（改 Vue 代码热更新）：

```bash
python run.py                     # 终端 1：后端 :5000
cd frontend && npm run dev        # 终端 2：Vite :5173（/api、/audio 自动代理）
```

### 页面功能

| 页面 | 功能 |
|------|------|
| 仪表盘 | 各集总览（语音块/字数/缓存段/成品状态）、缺失素材提示、新建/删除脚本 |
| 脚本编辑 | CodeMirror 语法高亮（`@` 指令/注释着色）、Ctrl+S 保存、右侧时间轴预览（含素材就绪检查与时长估算） |
| 构建任务 | 发起 build/tts/assemble/mix、dryrun/MiniMax 切换、试听 limit、强制重合成；分阶段进度条 + SSE 实时日志；任务可取消、自动排队互斥 |
| 素材库 | music/sfx 上传、时长探测、在线试听、删除 |
| 声音克隆 | 密钥/voice_id 状态一览、上传样本一键克隆（自动写回 .env）、语速调整 |
| 产物输出 | 成品试听下载、中间产物查看、按集语音缓存管理（单段删除强制重合成） |

### 技术说明

- 后端 `webapp/`（Flask）直接复用 `src/` 流水线函数；`tts/assemble/mix` 支持可选 `on_event` 回调，进度精确到每段语音 / 每秒混音，CLI 用法完全不受影响
- 构建任务在后台线程顺序执行（同时仅一个，防中间产物互相覆盖），状态与日志经 SSE（Server-Sent Events）推送到浏览器
- 仅监听 `127.0.0.1`，本地单人使用，无鉴权；请勿直接暴露到公网

## 口播稿标注语法

普通文字行 = 朗读内容；`#` 开头 = 注释；指令行以 `@` 开头：

| 指令 | 语法 | 说明 |
|------|------|------|
| 停顿 | `@pause 2` | 插入 2 秒静音（支持小数） |
| 插入型音频 | `@insert sfx/glasses.mp3 gain=-6 fade_out=1` | 顺序播放完再继续（片头曲、碰杯声） |
| 垫底型音频 | `@bed music/bgm.mp3 gain=-26 fade_in=8` | 循环垫底、说话时自动压低，直到 `@bed_stop`（环境音、BGM） |
| 垫底结束 | `@bed_stop` | 结束当前垫底层 |

- 文件路径相对 `audio/` 目录；`gain` 单位 dB；`fade_in/out` 单位秒
- 连续文字行合并为一个语音块（一次合成请求）；超过 350 字自动按句切分
- 完整示例见 [`script/episode01.txt`](script/episode01.txt)

## 命令一览

| 命令 | 作用 |
|------|------|
| `python -m src.cli parse <script>` | 解析脚本 → 时间轴 JSON |
| `python -m src.cli tts <script> [--limit N] [--force]` | 合成语音段（断点续传缓存） |
| `python -m src.cli assemble <script>` | 拼接语音主轨（语音+停顿+插入音效） |
| `python -m src.cli mix <script>` | ffmpeg 终混（垫底+闪避+响度归一） |
| `python -m src.cli build <script> [--limit N]` | 全流程一条命令 |
| `python -m src.cli clone <sample.wav>` | 上传声音样本，克隆音色 |
| `python run.py` | 启动 Web Studio（http://127.0.0.1:5000） |

所有命令均支持 `--provider dryrun|minimax`（默认读 `.env` 的 `TTS_PROVIDER`）。

## 工作原理

```
episodeNN.txt ──parse──▶ timeline（结构化时间轴）
                             │
                             ▼
              tts（MiniMax / dryrun，按集缓存于 audio/segments/{episode}/）
                             │
                             ▼
              assemble（pydub：语音 + 静音停顿 + 插入音效 → 主轨 wav
                        同时计算垫底音频的时间区间）
                             │
                             ▼
              mix（ffmpeg：垫底层定位 → sidechaincompress 闪避
                   → alimiter 限幅 → 双遍 loudnorm 归一 -16 LUFS）
                             │
                             ▼
                     episodeNN_final.mp3
```

关键设计：

- **停顿靠切段实现**：TTS 念不出 2-3 秒停顿，`@pause` 在组装阶段插入精确静音，这是成片节奏感的关键
- **两层音频模型**：`insert`（顺序播放）与 `bed`（垫底+闪避）覆盖播客全部配乐场景
- **双遍响度归一**：第一遍测量整片响度，第二遍 linear 模式精确拉升——比单遍动态模式更通透，无压缩感

Web Studio 在其上叠加一层：`webapp/services/runner.py` 以线程方式调用同一批函数，通过 `on_event` 回调收集进度（TTS 段级 / mix 秒级），经 SSE 推给浏览器；REST API 提供脚本、素材、缓存、克隆管理。

```
浏览器（Vue 3 SPA，frontend/）
   │ REST + SSE
   ▼
Flask（webapp/）── 后台线程顺序执行、全局互斥
   │ 直接复用（on_event 回调，CLI 兼容）
   ▼
src/ 流水线（parse → tts → assemble → mix）
```

## 多集生产

每期只需新建 `script/episode02.txt` 并重复 `build`。语音缓存按集隔离（`audio/segments/{episode}/`），各集互不影响；同集改稿只有文字变化的段落会重新合成。

## 常见问题

**Q: `No module named 'audioop'`**
Python 3.13 移除了该模块，`pip install audioop-lts`（requirements.txt 已包含条件依赖）。

**Q: ffmpeg 找不到**
确认 ffmpeg/ffprobe 可用；若装在 `~/miniconda3` 等位置但不在 PATH，脚本会自动探测注入。

**Q: push GitHub 超时（国内网络）**
配置 git 走本地代理（以 Clash 默认端口为例）：
```bash
git config --global http.https://github.com.proxy http://127.0.0.1:7897
```

**Q: 用记事本写的脚本报"指令变正文"**
已兼容 BOM；若仍异常，检查指令行是否以 `@` 开头、参数之间用空格分隔（报错信息带行号）。

**Q: 合成到一半断网了**
直接重跑 `build`——已完成的语音段有缓存，只补齐剩余部分。

**Q: Web 页面打开是 JSON 提示 "frontend not built"**
首次使用需构建前端：`cd frontend && npm install && npm run build`，然后重启 `python run.py`。

**Q: Web 构建任务点取消没立即停**
取消在语音段间生效；mix 阶段会先终止 ffmpeg 进程再退出，均在数秒内响应。

## 项目结构

```
podcast-pipeline/
├── script/          # 口播稿（每期一个 txt）
├── src/
│   ├── parser.py    # 标注脚本 → 时间轴
│   ├── tts.py       # MiniMax 合成 / dryrun / 声音克隆 / 按集缓存
│   ├── assemble.py  # 主轨组装（语音+停顿+插入音效）
│   ├── mix.py       # ffmpeg 终混（闪避+限幅+双遍响度归一）
│   └── cli.py       # 命令行入口
├── webapp/          # Web Studio 后端（Flask）
│   ├── api/         # scripts / jobs / assets / voice / outputs 蓝图
│   └── services/    # runner.py 后台任务执行器（互斥+SSE 事件）
├── frontend/        # Web Studio 前端（Vue 3 + Vite + Element Plus）
├── run.py           # Web Studio 一键启动
├── audio/
│   ├── segments/{episode}/   # 语音段缓存（自动管理）
│   ├── music/ · sfx/         # 素材（手动放入）
│   └── output/               # 中间产物与成品
├── .env.example     # 配置模板
└── requirements.txt
```
