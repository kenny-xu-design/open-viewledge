# Video Summary Skill

`video-summary-skill` 是一个本地优先的视频与音频知识提取工具。它把用户提供的本地媒体或公开在线视频转换为带时间戳、可追溯的知识包，并提供 Web 浏览和基于当前知识包字幕的 AI 对话。

当前稳定基线为 `v1.1`。`v1.2` 正在进行产品收尾，范围限于本地产品完整性，不包含 Scale 或 SaaS。

## 当前能力

主处理链路：

```text
本地视频/音频或公开 URL
-> LocalMediaSource / YtdlpSource
-> 优先获取平台字幕
-> 无字幕时 FFmpeg + 本地 faster-whisper
-> transcript.raw.jsonl / transcript.grouped.md / transcript.md
-> 时间轴与本地视频关键帧
-> DeepSeek 结构化文本分析
-> 标准知识包
-> CLI / Web 查看
```

Web 对话链路：

```text
knowledge_id
-> 当前知识包的分组字幕
-> 本地 BM25 风格检索
-> DeepSeek 或 Gemini 文本 Provider
-> 带时间戳引用的回答
-> chat.json
```

已实现：

- 本地视频和音频输入。
- YouTube、B站及其他 `yt-dlp` 支持的公开视频 URL。
- 平台字幕优先，无字幕时进入本地 ASR。
- 本地 `faster-whisper-small` 模型转写，不静默联网下载模型。
- `summary`、`tutorial`、`viral`、`close-reading` 分析模式。
- DeepSeek 结构化分析及 Pydantic 校验。
- 标准知识包、时间轴、关键帧和兼容 Markdown 输出。
- 三栏 Web 工作台、本地媒体播放、YouTube 官方 IFrame 预览和 B站官方 iframe 预览。
- 基于当前知识包字幕的真实 AI 对话、时间戳引用和按知识包保存的 `chat.json`。

尚未完成：

- 用户自写笔记目前仍是浏览器会话草稿，尚未持久化。
- Web 任务状态目前仅保存在进程内存中。
- Gemini 图片输入接口尚未完成；当前 Gemini 仅用于文本对话。
- Obsidian 目前仅提供兼容 Markdown 文件，不具备 Vault 同步或双向管理。
- B站官方 iframe 不提供本项目可依赖的可靠播放时间控制。

评论区分析已经停用，不属于当前产品功能。

## 合规边界

- 只处理用户主动提供的本地文件或公开媒体链接。
- 不绕过付费、访问控制、DRM 或平台权限。
- 不实现去水印、破解或批量搬运。
- 不提交 API Key、Cookie、账号凭据、模型文件、媒体文件和生成结果。
- 在线视频统一通过项目自身的 `yt-dlp` 适配路径处理，不依赖或调用 `bilibili-cli`。

## 环境要求

- Windows 或兼容 Python 3.12 的环境。
- Python 3.12。
- FFmpeg 和 FFprobe。
- 本地 faster-whisper 模型。
- DeepSeek API Key，仅在需要 AI 分析或 DeepSeek 对话时需要。
- Gemini API Key，仅在选择 Gemini 文本对话时需要。

安装 Python 依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

本地 Whisper 模型应位于：

```text
models/faster-whisper-small/
```

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

## API 配置

复制示例内容到项目根目录的 `.env`，只在本机填写真实 Key：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta

FFMPEG_PATH=
FFPROBE_PATH=
```

`.env` 已被 Git 忽略，`.env.example` 只保存空 Key 和非敏感默认值。不要把真实 Key 写入 `.env.example`、README、日志、知识包或提交记录。

当前 CLI 结构化分析后端仅支持 `deepseek`。Gemini 当前只出现在 Web 文本对话 Provider 中，不能用于 CLI 视频结构化分析，也不能进行视觉理解。

## CLI

查看帮助：

```powershell
.\.venv\Scripts\python.exe -m src.main --help
```

只读检查已有知识包：

```powershell
.\.venv\Scripts\python.exe -m src.main inspect "output\<knowledge-id>"
```

机器可读输出：

```powershell
.\.venv\Scripts\python.exe -m src.main inspect "output\<knowledge-id>" --json
```

检查命令不会修改历史输出。返回码：`0` 表示有效，`1` 表示存在兼容性警告，`2` 表示知识包无效。

本地视频完整处理：

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --file "E:\path\to\video.mp4" `
  --backend deepseek `
  --mode summary
```

只生成字幕，不调用 LLM：

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --file "E:\path\to\video.mp4" `
  --no-summary
```

30 秒链路验证：

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --file "E:\path\to\video.mp4" `
  --no-summary `
  --sample-seconds 30
```

YouTube 或通用公开视频：

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --backend deepseek `
  --mode tutorial
```

B站：

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "https://www.bilibili.com/video/BV..." `
  --backend deepseek `
  --mode summary
```

Obsidian 兼容 Markdown 副本：

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --url "公开视频链接" `
  --backend deepseek `
  --export obsidian
```

这里的 `obsidian` 表示生成兼容 Markdown 副本 `export_note.md`，不表示自动写入 Vault。

### CLI 参数

- `--url`：公开在线视频 URL。
- `--file`：本地媒体路径。
- `--lang`：字幕或转写语言。
- `--backend`：当前只接受 `deepseek`。
- `--mode`：`summary`、`tutorial`、`viral`、`close-reading`。
- `--no-summary`：跳过 LLM 分析。
- `--sample-seconds`：只处理媒体开头指定秒数。
- `--no-frames`：跳过关键帧生成。
- `--export obsidian`：生成 Obsidian 兼容 Markdown 副本。
- `--comments`：仅为旧命令兼容保留，当前会提示已停用。

## Web UI

推荐使用项目启动脚本：

```powershell
.\start_web.ps1
```

或：

```bat
start_web.bat
```

等价命令：

```powershell
.\.venv\Scripts\python.exe -m src.web --host 127.0.0.1 --port 5188
```

打开：

```text
http://127.0.0.1:5188/
```

Web 后台任务使用 Web 进程自身的 `sys.executable` 启动 `src.main`。通过上述脚本启动时，会固定使用项目 `.venv`。

Web 当前支持：

- 浏览已有知识包。
- 创建 URL 或本地路径处理任务。
- 查看摘要、章节、时间轴、字幕和关键帧。
- 播放本地媒体。
- 使用 YouTube 官方 IFrame API 预览。
- 使用 B站官方 iframe 预览。
- 对当前知识包进行字幕检索和 AI 对话。
- 按 `knowledge_id` 加载和保存 `chat.json`。
- 调整三栏模块顺序和宽度。

当前笔记编辑区不会写入磁盘；刷新页面或重启服务后草稿可能丢失。

## 知识包结构

每个稳定知识包位于：

```text
output/<title>_<source-id>/
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
audio/audio_16k.wav
frames/*.jpg
```

`analysis.json` 应记录 `status`、`provider`、`model`、`usage` 和结构化分析结果。`manifest.json` 记录各处理阶段、Provider 尝试、错误和输出文件。

新知识包还会在 manifest 中明确记录 `analysis_status` 和 `analysis_error`。空 `analysis.json`、无有效字幕、无时间轴或缺少必需文件不会被视为成功知识包。

## 常见错误

### 未找到 yt-dlp

确认使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -c "import yt_dlp; print('yt-dlp OK')"
```

缺失时执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 未找到 FFmpeg

错误会说明缺少 `ffmpeg` 还是 `ffprobe`。可设置配置项、环境变量、PATH，或使用项目本地工具目录。例如：

```powershell
$env:FFMPEG_PATH = "C:\tools\ffmpeg\bin\ffmpeg.exe"
$env:FFPROBE_PATH = "C:\tools\ffmpeg\bin\ffprobe.exe"
```

项目不会静默下载程序或修改系统 PATH。

### 未找到本地 Whisper 模型

项目不会自动联网下载。按照“环境要求”中的命令显式下载到 `models/faster-whisper-small`。

### DeepSeek 未配置

在被 Git 忽略的项目根目录 `.env` 中设置 `DEEPSEEK_API_KEY`。不要把 Key 粘贴到命令、聊天记录或仓库文件中。

### 在线视频无法预览

视频可能禁止嵌入、需要登录、受地区限制或平台 iframe 不提供控制能力。知识包、字幕和分析仍可正常查看；必要时使用“在原网站打开”。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m src.main --help
.\.venv\Scripts\python.exe -m src.web --help
```

当前 `v1.1` 基线为 97 项单元测试通过。新增功能不得减少现有覆盖。

## 项目文档

- [当前状态](docs/CURRENT_STATE.md)
- [架构](docs/ARCHITECTURE.md)
- [路线图](docs/ROADMAP.md)
- [长期决策](docs/DECISIONS.md)
- [历史文档归档](docs/archive/)

## 已知限制

- B站官方 iframe 无可靠的程序化时间跳转和播放同步。
- Gemini 视觉输入未实现，也未进行真实 API 验证。
- 自写笔记和 Web 任务历史尚未持久化。
- Obsidian 仅为兼容 Markdown 导出，不是 Vault 数据层。
- 通用网页正文采集尚未实现；当前 URL 输入面向 `yt-dlp` 支持的视频平台。
