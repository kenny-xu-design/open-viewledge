# Viewledge

Viewledge 是一款正在私有开发中的本地优先 AI 视频解析与知识沉淀产品，支持 YouTube、B站和本地媒体，可生成结构化摘要、教程步骤、传播分析、深度精读、评论洞察及 Obsidian-ready Markdown knowledge packages。

**当前测试版本：v1.4.5 内部便携 Beta**

当前核心源码暂未公开。本仓库是私有开发仓库；v1.4.5 源码便携包仅用于内部和可信测试，不应上传到公开 GitHub Release。未来公开仓库只承担产品展示、下载、反馈和版本说明；公开产品包将在后续版本中去除可直接复用的核心源码。

## 功能概览

- 处理 YouTube、B站及其他 `yt-dlp` 支持的公开视频链接。
- 处理本地视频和音频，并在没有平台字幕时使用本地语音转写。
- 提供标准摘要、教程提取、爆款分析和深度精读四种分析模式。
- 根据视频时长和内容密度生成章节、高光与时间戳。
- 可选同步公开评论，并独立生成评论区洞察，不混入主报告。
- 在 Web 中预览视频、跳转时间戳、进行 AI 对话和保存用户笔记。
- 导出普通 Markdown、Obsidian 兼容知识包及结构化 JSON 数据。

## 快速开始

### Windows 内部测试包用户

准备条件：

- Windows 10 或 Windows 11。
- 已安装 Python 3.12，并勾选安装程序中的“Add Python to PATH”。
- 首次启动时保持网络连接，以便安装 Python 依赖。

启动步骤：

1. 获取内部测试 ZIP 并完整解压。
2. 双击项目根目录中的 `start_web.bat`。
3. 首次启动会自动创建项目专用的 `.venv` 运行环境并安装依赖。
4. 浏览器打开后，进入“API 配置”填写自己的模型信息。
5. 点击“新总结”，输入公开视频链接或选择本地媒体并开始处理。

内部测试包用户不需要安装 Git 或 GitHub Desktop，不需要把项目放在固定目录。请将 ZIP 解压到任意普通、可写目录，不要直接在压缩包内部运行 `start_web.bat`。

Web 默认地址：

```text
http://127.0.0.1:5188/
```

关闭启动脚本的命令窗口会停止本地 Web 服务。

## API 配置

项目当前支持：

- **DeepSeek / OpenAI Compatible**：用于文字摘要、评论洞察和 AI 对话。
- **Gemini**：用于视频视觉理解和视频对话。
- **Groq Speech-to-Text**：用于没有平台字幕时的云端快速转写。

启动 Web 后打开“API 配置”，填写对应的 API Key、模型名和服务地址，并先使用“测试连接”确认配置可用。Groq 的测试连接只验证 Key、网络和模型可见性，不上传音频。

API Key 默认只用于当前本地运行会话。页面刷新后，只要后端服务仍在运行即可继续使用；服务重启后需要重新填写。完整密钥不会返回给页面，也不应写入 Git、知识包、Markdown、导出文件或问题反馈。

DeepSeek、Gemini 和 Groq 均为可选第三方服务，其免费额度、价格、可用区域和
服务条款由对应服务商决定，项目不承诺永久免费。使用前请在服务商控制台确认
当前价格和额度；不配置云端服务时仍可使用平台字幕、本地 faster-whisper、
知识包浏览和导出等本地能力。

命令行和开发环境仍可使用项目根目录中被 Git 忽略的 `.env`；普通 Web 用户无需手动编辑 `.env`。

## 创建视频任务

1. 在 Web 左上角点击“新总结”。
2. 输入 YouTube、B站或其他支持的公开视频链接，或选择本地媒体。
3. 选择分析模式与处理模式。
4. 按需开启公开评论同步。
5. 点击“开始处理”，等待字幕、分析和知识包生成完成。

平台没有字幕时，默认使用 Groq 云端快速转写，也可为当前任务选择本地 GPU 或本地 CPU。处理本地媒体或无字幕视频通常需要 FFmpeg；评论关闭、平台限制或无法读取评论时，评论同步会跳过，但不影响主摘要。

## 分析模式

- **标准摘要**：适合资讯、访谈、介绍和一般知识视频。
- **教程提取**：适合软件、编程、设计和制作教程。
- **爆款分析**：适合热门视频、广告、短视频和自媒体内容。
- **深度精读**：适合课程、演讲、长访谈和复杂观点内容。

仅“教程提取 + 完整处理”会为关键教程步骤生成截图。标准摘要、爆款分析和深度精读不会导出分析截图。

## 快速处理与完整处理

- **快速处理**：优先生成字幕与文字分析，适合快速阅读；无字幕时只请求音频，不执行视觉分析或教程截图。
- **完整处理**：在文字结果基础上继续执行可用的视觉分析；教程提取模式可生成关键步骤截图。

长视频会根据时长和内容密度自动采用窗口化或分层分析，不需要用户手动设置分段。

## 查看与导出结果

处理完成后可以：

- 在知识记录中查看摘要、章节、时间轴、字幕、高光和评论区。
- 点击时间戳在当前预览播放器中跳转。
- 使用右侧 AI 对话查询当前视频内容。
- 保存个人笔记。
- 预览、复制或下载 Markdown。
- 生成 Obsidian 兼容知识包。

评论区与高光片段是视频下方的同级功能；评论洞察不会写入左侧全文总结。Obsidian 导出目前是兼容 Markdown，不提供 Vault 双向同步。

## 常见问题

### 双击 `start_web.bat` 后无法启动

确认已经完整解压 ZIP，并安装 Python 3.12。脚本必须位于项目根目录，旁边应能看到 `requirements.txt` 和 `src` 文件夹。

### 首次启动时间较长

首次运行需要创建 `.venv` 并从网络安装依赖，后续启动会直接复用已有环境。

### 本地视频或无字幕视频无法处理

Windows 发行包已内置 FFmpeg 和 FFprobe，不需要单独配置。源码运行时也可将其加入系统 `PATH`，或放入 `tools/ffmpeg/bin/`。

### AI 分析或对话失败

打开 Web 中的“API 配置”，检查 API Key、Base URL 和模型名，并先执行“测试连接”。程序不会在错误提示中回显完整密钥。

### 在线视频无法预览

视频可能禁止嵌入、需要登录、存在地区限制，或平台 iframe 不支持完整控制。知识包、字幕和分析仍可能正常生成，可使用“在原网站打开”。

## 安全说明

- 只处理用户主动提供的本地文件或公开媒体链接。
- 不绕过付费、访问控制、DRM 或平台权限。
- 不实现去水印、破解或批量搬运。
- 不提交 API Key、Cookie、账号凭据、模型文件、媒体文件和生成结果。
- 在线视频统一通过项目自身的 `yt-dlp` 适配路径处理，不依赖或调用 `bilibili-cli`。

## 开发者说明

以下内容面向需要使用 CLI、调试依赖、检查数据契约或参与开发的用户。普通 ZIP 用户只需按照“快速开始”使用 `start_web.bat`。

### 环境要求

- Windows 或兼容 Python 3.12 的环境。
- Python 3.12。
- FFmpeg 和 FFprobe。
- 本地 faster-whisper 模型。
- DeepSeek API Key，仅在需要 AI 分析或 DeepSeek 对话时需要。
- Gemini API Key，仅在完整模式视觉分析或选择 Gemini 视频对话时需要；未配置时文本知识包仍可生成。

安装 Python 依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

默认依赖不安装 NVIDIA CUDA、cuBLAS 或 cuDNN 运行库。平台字幕、Groq 云端转写
和本地 CPU 转写不需要 CUDA。需要本地 GPU 转写的用户应自行安装与显卡驱动及
CTranslate2 版本兼容的 CUDA 运行库；项目启动脚本不会替用户下载或修改 CUDA。

本地 Whisper 模型应位于：

```text
models/faster-whisper-small/
```

本地 ASR 默认使用 `ASR_PROFILE=balanced`，并按实际设备能力选择：

```text
RTX / CUDA 可用且显存充足
-> turbo + CUDA FP16（仅在本地 turbo 模型已安装时）
-> small + CUDA FP16
-> small + CUDA INT8_FLOAT16
-> small + CPU INT8
```

另外支持 `fast` 和 `quality`。`quality` 只有用户明确选择时才会尝试本地
`large-v3`；所有模型均使用 `local_files_only`，缺失时不会自动下载。
`task=translate` 不使用 turbo。

可在 `.env` 中覆盖：

```dotenv
ASR_PROFILE=balanced
ASR_MODEL=
ASR_DEVICE=
ASR_COMPUTE_TYPE=
ASR_TASK=transcribe
```

GPU 路由同时检查 CTranslate2 CUDA 设备、支持的计算精度、可用显存、模型实际
加载和隔离的首批推理。Windows CUDA 转写还需要 CTranslate2 兼容的 CUDA 12
cuBLAS 与 cuDNN 运行库；缺失或 OOM 时会降低批大小/精度并安全回退 CPU，不会
让整个任务失败。

`balanced` 和 `quality` 会记录每个字幕段的 log probability、压缩率、
无语音概率和语言置信度，对低质量区间最多进行有限次局部重试。整条视频低置信
片段比例过高时只提示用户选择 `quality`，不会自动下载大型模型或重跑整条视频。

至少需要：

```text
model.bin
config.json
tokenizer.json
vocabulary.txt
```

模型不存在时可由用户显式执行：

```powershell
hf download Systran/faster-whisper-small --local-dir models/faster-whisper-small
```

项目不会静默下载模型。

### FFmpeg

FFmpeg 和 FFprobe 使用同一套项目级发现机制，优先级为：

```text
config.example.json 中的 ffmpeg_path / ffprobe_path
-> FFMPEG_PATH / FFPROBE_PATH
-> 当前 PATH
-> 项目内允许的 tools/、bin/、tools/ffmpeg/bin/ 等目录
-> 明确错误
```

示例环境变量：

```dotenv
FFMPEG_PATH=C:\tools\ffmpeg\bin\ffmpeg.exe
FFPROBE_PATH=C:\tools\ffmpeg\bin\ffprobe.exe
```

变量也可以指向包含对应程序的目录。项目不会修改系统 PATH，也不会自动下载二进制。

仅查看 `--help` 不需要 FFmpeg。实际进行音频提取、媒体规范化或关键帧生成时才解析 FFmpeg。FFprobe 状态会独立显示，便于诊断后续媒体探测能力。

### 环境变量配置

复制示例内容到项目根目录的 `.env`，只在本机填写真实 Key：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta

GROQ_API_KEY=
CLOUD_ASR_PROVIDER=groq
CLOUD_ASR_MODEL=whisper-large-v3-turbo
CLOUD_ASR_TIMEOUT_SECONDS=300
CLOUD_ASR_MAX_RETRIES=2
CLOUD_ASR_FILE_LIMIT_MB=25
CLOUD_ASR_CHUNK_OVERLAP_SECONDS=2

FFMPEG_PATH=
FFPROBE_PATH=
VIEWLEDGE_HTTP_PROXY=
```

知识包默认写入项目根目录的 `output/`。如需让不同解压版本、不同启动端口或
CLI/Web 共用同一批知识包，可在启动前设置共享输出目录：

```powershell
$env:VIEWLEDGE_OUTPUT_ROOT = "$env:LOCALAPPDATA\Viewledge\knowledge"
.\start_web.ps1
```

也可以把 `config.example.json` 中的 `output_dir` 改成绝对路径，并在所有版本中
使用同一个值。环境变量 `VIEWLEDGE_OUTPUT_ROOT` 优先级高于配置文件；未设置时
保持默认 `output/` 行为。

`.env` 已被 Git 忽略，`.env.example` 只保存空 Key 和非敏感默认值。不要把真实 Key 写入 `.env.example`、README、日志、知识包或提交记录。

如果浏览器可以访问视频平台或模型服务，但 Python、`yt-dlp` 报
`WinError 10013`、连接超时或网络不可用，可为 Viewledge 单独指定本机 HTTP
代理：

```powershell
$env:VIEWLEDGE_HTTP_PROXY = "http://127.0.0.1:7897"
.\start_web.ps1
```

也可将 `VIEWLEDGE_HTTP_PROXY` 设置为用户级环境变量，使后续启动和新版本继续
生效。程序会把它映射给 `yt-dlp`、DeepSeek、Gemini 等 Python 网络客户端；
已有的 `HTTP_PROXY` / `HTTPS_PROXY` 优先，不会被覆盖。代理地址在运行状态中
只显示协议、主机和端口，不显示用户名或密码。

当前 CLI 结构化文本分析后端仅支持 `deepseek`。完整模式会在本地视频抽帧后尝试可选 Gemini 视觉分析；Web 选择 Gemini 对话时会依次尝试公开 YouTube URL、已有或新上传的本地视频、关键帧+文本和纯文本。视频上传仅在用户明确选择 Gemini 且知识包有本地视频时发生。

Web 的“API 配置”入口用于本地交互。API Key 默认只保存在当前 Web 后端进程内存中，页面刷新后只要服务未重启即可继续使用；服务重启后需要重新填写。状态接口只返回是否已配置、配置来源、模型、Base URL 和 Key 尾号 4 位，不返回完整 Key。API Key 不写入 `localStorage`、`sessionStorage`、Web job store、知识包、Markdown、导出文件或仓库文件。

### CLI

公开命令统一为：

```text
analyze / inspect / export / resume / doctor / config
```

所有命令支持 `--json`；长任务 `analyze`、`resume` 额外支持 `--jsonl`。stdout 只输出结果或 JSON，诊断与人工日志写入 stderr。旧的根级 `--url` / `--file` 用法仅为兼容保留，并会明确提示废弃。

查看帮助：

```powershell
.\.venv\Scripts\python.exe -m src.main --help
```

查看版本：

```powershell
.\.venv\Scripts\python.exe -m src.main --version
```

只读检查已有知识包：

```powershell
.\.venv\Scripts\python.exe -m src.main inspect "output\<knowledge-id>"
```

机器可读输出：

```powershell
.\.venv\Scripts\python.exe -m src.main inspect "output\<knowledge-id>" --json
```

检查命令不会修改历史输出。返回码：`0` 表示有效，`1` 表示存在兼容性警告，`6` 表示知识包无效或损坏。

本地视频完整处理：

```powershell
.\.venv\Scripts\python.exe -m src.main analyze `
  --file "E:\path\to\video.mp4" `
  --backend deepseek `
  --mode summary
```

只生成字幕，不调用 LLM：

```powershell
.\.venv\Scripts\python.exe -m src.main analyze `
  --file "E:\path\to\video.mp4" `
  --no-summary
```

30 秒链路验证：

```powershell
.\.venv\Scripts\python.exe -m src.main analyze `
  --file "E:\path\to\video.mp4" `
  --no-summary `
  --sample-seconds 30
```

YouTube 或通用公开视频：

```powershell
.\.venv\Scripts\python.exe -m src.main analyze `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --backend deepseek `
  --mode tutorial
```

B站：

```powershell
.\.venv\Scripts\python.exe -m src.main analyze `
  --url "https://www.bilibili.com/video/BV..." `
  --backend deepseek `
  --mode summary
```

Obsidian 兼容 Markdown 副本：

```powershell
.\.venv\Scripts\python.exe -m src.main analyze `
  --url "公开视频链接" `
  --backend deepseek `
  --export obsidian
```

这里的 `obsidian` 表示生成兼容 Markdown 副本 `export_note.md`，不表示自动写入 Vault。通过 Web 保存的 `user_notes.md` 会合并到该兼容副本中。

#### CLI 参数

- `--url`：公开在线视频 URL。
- `--file`：本地媒体路径。
- `--lang`：字幕或转写语言。
- `--backend`：当前只接受 `deepseek`。
- `--mode`：`summary`、`tutorial`、`viral`、`close-reading`。
- `--processing-profile`：`fast` 或 `complete`；默认 `complete`。`fast` 优先生成可读文本，无字幕时只请求音频，并跳过关键帧阶段。
- `--no-summary`：跳过 LLM 分析。
- `--asr-route`：无平台字幕时选择 `cloud`、`local_gpu` 或 `local_cpu`；旧请求默认 `cloud`。
- `--no-asr-fallback`：关闭云端到本地 GPU/CPU，或本地 GPU 到 CPU 的安全回退。
- `--sample-seconds`：只处理媒体开头指定秒数。
- `--no-frames`：跳过关键帧生成。
- `--export obsidian`：生成 Obsidian 兼容 Markdown 副本。
- `--comments`：同步公开评论并生成独立评论区洞察。该功能只读取公开评论；失败会记录为警告，不会让主摘要任务失败。
- `--json`：输出带 Schema 版本的单个 JSON 结果。
- `--jsonl`：长任务逐行输出生命周期事件。

环境诊断与有效配置：

```powershell
.\.venv\Scripts\python.exe -m src.main doctor --json
.\.venv\Scripts\python.exe -m src.main config --json
```

失败任务可使用 `analyze` 返回的 `task_id` 恢复：

```powershell
.\.venv\Scripts\python.exe -m src.main resume "<task-id>" --jsonl
```

### Web UI 技术说明

Windows ZIP 用户和普通本地用户推荐直接运行：

```bat
start_web.bat
```

该脚本会从自身所在的仓库根目录启动，首次运行时检查 Python 3.12、创建 `.venv` 并安装依赖，不依赖 Git、分支名称或固定磁盘路径。

已准备好开发环境时，也可以使用：

```powershell
.\start_web.ps1
```

或直接执行：

```powershell
.\.venv\Scripts\python.exe -m src.web --host 127.0.0.1 --port 5188
```

打开：

```text
http://127.0.0.1:5188/
```

Web 后台任务使用 Web 进程自身的 `sys.executable` 启动 `src.main`。通过上述脚本启动时，会固定使用项目 `.venv`。

Web、CLI 和导出命令使用同一套知识包输出目录解析规则：优先读取
`VIEWLEDGE_OUTPUT_ROOT`，否则使用配置中的 `output_dir`。启动端口只影响浏览器
本地 UI 状态，不决定知识包读取位置。

Web 当前支持：

- 浏览已有知识包。
- 创建 URL 或本地路径处理任务。
- 查看摘要、章节、时间轴、字幕和关键帧。
- 播放本地媒体。
- 使用 YouTube 官方 IFrame API 预览。
- 使用 B站官方 iframe 预览。
- 对当前知识包进行字幕检索和 AI 对话。
- AI 分析失败时，使用结果区的“重新生成摘要”按钮复用已有字幕，只重跑 AI 分析。
- 在资源库中进入删除模式，多选知识记录并经过最终确认后永久删除对应知识包。
- 按 `knowledge_id` 加载和保存 `chat.json`。
- 按 `knowledge_id` 加载和原子保存 `user_notes.md`。
- 查看服务重启后仍保留的最近任务；异常中断任务显示为 `interrupted`。
- 调整三栏模块顺序和宽度。
- 通过原创纵向导出面板预览、复制或下载 Markdown，并按本地配置安全写入 Obsidian Vault。
- 显式同步公开评论，并在知识页与导出中独立展示评论区洞察。知识页视频下方的功能区使用“评论区 / 高光片段”同级 Tab；评论内容不会写入左侧“全文总结”。
- 通过“API 配置”填写或测试 DeepSeek/OpenAI-compatible、Gemini 和 Groq。Web 会话配置优先于环境变量；未填写时继续兼容 `.env` / 环境变量；非敏感默认模型和 Base URL 来自项目默认值。

笔记编辑区在停止输入 800 ms 后保存，切换知识包前也会尝试完成保存。保存笔记时会同步刷新 `export_note.md`。

B站预览使用官方 iframe。点击摘要、字幕或聊天引用中的时间戳时，Web UI 会在原预览区域用当前 `bvid`、`p` 等参数重载 iframe，并更新 `t=<秒数>`；外部原视频链接保留为单独操作。

本地视频预览默认使用原始比例和 `object-fit: contain`。播放器工具栏可切换原始比例、16:9、4:3、1:1、9:16，以及适应/填充显示模式；切换不会主动重置播放时间或暂停状态。

“重新生成摘要”仅在分析失败或知识包分析状态异常时显示。使用前需通过 Web“API 配置”或项目环境变量提供可用的 DeepSeek 配置；重试不会重新下载媒体、提取字幕或生成关键帧。

### 数据契约与分析输出

四种模式都使用重大结构调整前的扁平公共骨架：`summary`、`terminology`、`highlights`、`thoughts` 和 `chapters`。`tutorial`、`viral` 和 `close-reading` 仅在 `content` 中保存各自有实际内容的专属补充；缺失的可选栏目不会用“未明确说明”占位。共同外壳记录 `schema_version`、`analysis_profile`、`processing_profile`、来源、生成信息、分段策略和警告；`generation.comments_included` 固定为 `false`，评论区洞察不会写入主报告。Profile 统一按“用户显式选择 → 知识包已有值 → 自动识别 → summary”解析，识别失败不会导致任务失败。

长视频分析会写入 `analysis.segmentation` 元数据，包括 `policy_version=adaptive-v2`、时长桶、窗口长度、重叠、建议章节/高光范围、实际数量、覆盖率和最大空档。30 分钟以上的密集字幕视频优先使用窗口分析；60 分钟以上密集视频默认使用分层语义 Map/Reduce；低密度内容允许低于建议数量范围，但不会机械插入假章节。

- `summary`：摘要、亮点、思考、视频章节总结、原文资料。
- `tutorial`：在公共骨架中按需插入教程目标、最终成果、前置条件、工具与材料、流程总览、完整教程步骤、关键参数与设置、常见错误与排查、完成验收清单、可复用命令或模板、教程局限。仅 `tutorial + complete` 允许生成并导出 `assets/tutorial/` 步骤截图。
- `viral`：在公共骨架中按需插入内容定位、目标受众、标题与封面承诺、前 30 秒钩子、内容结构、节奏与留存设计、情绪与叙事机制、视觉包装与剪辑、互动与传播设计、可复用内容公式、可借鉴点、风险与局限。
- `close-reading`：在公共骨架中按需插入核心命题、关键概念、论证地图、证据评估、隐含假设、可能的反方观点、论证局限、视觉证据、延伸联系、待核查事实；公共 `chapters` 字段承载逐章精读。

四种模式中的“专业术语”均采用同一规则：本次分析识别到 3～8 个不同、可靠且与核心内容直接相关的术语时，模块显示在“摘要”之后；少于 3 个时整个模块隐藏。历史 v1.4.3 `content` 知识包继续兼容读取，但新结果不会恢复固定空栏目或“一句话”展示模块。

时间戳由统一模块格式化并生成平台链接：YouTube 和 B站链接保留既有查询参数并替换 `t`；Web 预览内点击时间戳统一进入 `seekPreview(seconds)`，本地媒体使用 `currentTime`，YouTube 使用 IFrame API，B站在原预览区域重载带 `t=<秒数>` 的 iframe。

导出产物是普通 UTF-8 `.md` 文件；`.obsidian` 是 Vault 配置目录，程序不会写入其中。下载 Markdown 不要求安装 Obsidian。Vault 直接写入仅适用于本地部署，服务端只读取本地配置，前端不能提交任意路径。组合导出支持摘要、AI 对话、评论区洞察和原始用户笔记；关键帧只读取既有产物，不重新调用模型。

CLI 示例：

```powershell
python -m src.main export --knowledge-id "<id>" --format markdown --preset summary-chat --json
python -m src.main export --knowledge-id "<id>" --format obsidian --preset full --json
```

知识记录删除是永久操作。Web UI 会先显示可勾选标记，再要求在确认弹窗中确认；正在处理中的记录不会被删除。

### 知识包结构

每个稳定知识包位于：

```text
<output_dir>/<title>_<source-id>/
```

核心文件：

```text
index.md
metadata.json
manifest.json
analysis.json
timeline.json
source.md
transcript.raw.jsonl
transcript.grouped.md
transcript.md
```

按条件生成：

```text
summary.md
chapter_summary.md
highlight_notes.md
export_note.md
chat.json
user_notes.md
comments.json
comments.md
comment_insights.json
comment_insights.md
audio/audio_16k.wav
frames/*.jpg
```

`analysis.json` 应记录 `status`、`provider`、`model`、`usage` 和结构化分析结果。`manifest.json` 记录各处理阶段、Provider 尝试、错误和输出文件。

新知识包还会在 manifest 中明确记录 `analysis_status` 和 `analysis_error`。空 `analysis.json`、无有效字幕、无时间轴或缺少必需文件不会被视为成功知识包。

### 开发者故障排查

#### 未找到 yt-dlp

确认使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -c "import yt_dlp; print('yt-dlp OK')"
```

缺失时执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

#### 未找到 FFmpeg

错误会说明缺少 `ffmpeg` 还是 `ffprobe`。可设置配置项、环境变量、PATH，或使用项目本地工具目录。例如：

```powershell
$env:FFMPEG_PATH = "C:\tools\ffmpeg\bin\ffmpeg.exe"
$env:FFPROBE_PATH = "C:\tools\ffmpeg\bin\ffprobe.exe"
```

项目不会静默下载程序或修改系统 PATH。

#### 未找到本地 Whisper 模型

项目不会自动联网下载。按照“环境要求”中的命令显式下载到 `models/faster-whisper-small`。

#### DeepSeek 未配置

在被 Git 忽略的项目根目录 `.env` 中设置 `DEEPSEEK_API_KEY`。不要把 Key 粘贴到命令、聊天记录或仓库文件中。

如果 DeepSeek 返回 HTTP 400，优先检查 `.env` 中的 `DEEPSEEK_MODEL` 是否为当前账号支持的模型名。程序会在错误信息中保留经过脱敏的上游原因，例如模型名不受支持，但不会输出 API Key。

Web 端也可以打开“API 配置”检查 DeepSeek/OpenAI-compatible 的 API Key、Base URL 和 Model。测试连接只发送最小请求，不启动完整视频分析。

#### 在线视频无法预览

视频可能禁止嵌入、需要登录、受地区限制或平台 iframe 不提供控制能力。知识包、字幕和分析仍可正常查看；必要时使用“在原网站打开”。B站 iframe 的播放、倍速和时间跳转由播放器自身控制。

### 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m src.main --help
.\.venv\Scripts\python.exe -m src.web --help
```

前端脚本和 Git 差异检查：

```powershell
node --check src/web_ui/app.js
git diff --check
```

发布前应运行全量测试、语法检查和人工浏览器验收；README 不记录易失效的历史测试数量。

## 版本与文档

- [变更记录](CHANGELOG.md)
- [当前项目状态](docs/PROJECT_STATE.md)
- [总路线图](docs/MASTER_ROADMAP.md)
- [仓库边界](docs/REPO_BOUNDARY.md)
- [API 契约](docs/API_CONTRACTS.md)
- [测试基线](docs/TEST_BASELINE.md)
- [下一任务](docs/NEXT_TASK.md)
- [旧状态入口](docs/CURRENT_STATE.md)
- [架构](docs/ARCHITECTURE.md)
- [旧路线图入口](docs/ROADMAP.md)
- [长期决策](docs/DECISIONS.md)
- [历史文档归档](docs/archive/)

## 已知限制

- B站官方 iframe 通过重载 `t=<秒数>` 实现预览区时间戳跳转；实际播放行为仍受官方播放器嵌入能力限制。
- Gemini 视频和视觉路径已经形成可操作流程并完成 mock 验证；当前环境未配置 Gemini，因此仍需真实 API、额度、长视频和 URL 拒绝场景验收。
- 评论同步依赖公开平台和 `yt-dlp` 当前能力；关闭评论、平台限制或提取器不返回评论时会跳过评论产物，主知识包仍可用。
- Obsidian 仅为兼容 Markdown 导出，不是 Vault 数据层。
- 通用网页正文采集尚未实现；当前 URL 输入面向 `yt-dlp` 支持的视频平台。

## 授权状态

Viewledge 当前处于私有开发和内部测试阶段，核心源码暂未公开。正式公开产品包、公开展示仓库和外部分发授权仍需单独完成许可证与发布策略审查。

仓库中现有的 [LICENSE](LICENSE) 和 [商业授权说明](COMMERCIAL-LICENSE.md) 属于历史授权材料和待审查文件。本轮不删除、不替换，也不将其作为未来公开产品包的最终授权承诺。正式外部分发前，需要明确 Viewledge 自身代码、品牌、发行包和第三方组件的授权边界。

v1.4.5 源码便携包仅用于内部和可信测试，不应公开传播或上传到公开 Release。未来公开产品包计划去除可直接复用的核心源码，但这不构成“无法逆向”或“绝对保护源码”的承诺。

第三方库、模型、工具、API、平台服务和媒体内容仍分别受其自身许可证与
服务条款约束。

版权所有 © 2026 kenny-xu-design。未经明确书面许可，Viewledge 名称、中文名称、Logo 或其他品牌标识不得用于混淆来源的再包装或分发。
