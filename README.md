# video-summary-skill

`video-summary-skill` 是一个本地 Python 深度媒体信息处理项目，用于把公开视频链接、本地视频或音频转换成可追溯的知识包。当前统一路径是“来源识别 -> 字幕优先 -> 无字幕时本地 ASR -> 逐句数据 -> 分组字幕 -> 时间轴/关键帧 -> 结构化分析 -> Markdown 导出”。CLI 与 Web UI 共用同一个 `PipelineOrchestrator`。

现在项目也包含一个 Codex Agent Skill：`.agents/skills/video-summary/SKILL.md`。Codex 可以调用现有 Python CLI 先生成 `transcript.md`，再根据 `prompts/summary_prompt.md` 生成 `summary.md`。

## 当前基线状态

当前版本已具备本地视频与在线字幕处理、`faster-whisper` 本地转写、三栏 Web UI、时间轴、知识包输出和 DeepSeek 结构化文本分析。

尚未完成：AI 上下文对话、自写笔记持久化、Obsidian 数据层和 Gemini 多模态分析。

本地资源说明：`models/`、`output/` 和 `.env` 不纳入 Git；使用者需要自行安装依赖并准备本地模型。当前环境的 FFmpeg 尚未加入 `PATH`，这不影响代码基线，但在处理无字幕视频或本地媒体前必须先完成 FFmpeg 配置。

## 功能说明

- B站、YouTube 和其他公开视频统一使用项目自己的 yt-dlp Source，不调用外部平台 CLI。
- 优先提取平台字幕；没有字幕时才下载 audio-only 并进入本地 ASR。
- 输入本地 mp4 / mp3 / wav / m4a 等文件，使用 FFmpeg 提取音频后转写。
- 有字幕时清洗 `.srt` / `.vtt` 并生成 `transcript.md`。
- 无字幕时用 FFmpeg 提取 16kHz 单声道 wav，再用 `faster-whisper` 转写。
- 使用 DeepSeek 生成结构化 `analysis.json` 及中文摘要、高光、章节和模式报告。
- 评论功能已退出默认处理管线；`--comments`仅为旧命令兼容保留并会显示停用提示。
- 使用`--sample-seconds 30`可仅处理媒体开头30秒，适合验证无字幕 ASR 链路。
- 未配置 `DEEPSEEK_API_KEY` 时，字幕仍会保留，`analysis.json` 会明确记录为失败状态。

## 安装 Python 依赖

建议使用 Python 3.10+。

```bash
cd video-summary-skill
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux 激活虚拟环境：

```bash
source .venv/bin/activate
```

## 安装 FFmpeg

Windows 可使用：

```powershell
winget install Gyan.FFmpeg
```

macOS 可使用：

```bash
brew install ffmpeg
```

Linux 可使用：

```bash
sudo apt-get install ffmpeg
```

安装后运行：

```bash
ffmpeg -version
```

如果命令不存在，请确认 FFmpeg 已加入 PATH。

## B站来源说明

项目自己的`BilibiliAdapter`只负责识别 B站链接或 BV 号并委托 yt-dlp，不查找或调用外部平台命令。新 Pipeline 直接使用统一的`YtdlpSource`。

## 配置 .env

复制示例文件：

```bash
copy .env.example .env
```

macOS / Linux：

```bash
cp .env.example .env
```

如需让 CLI 自己生成 `summary.md`，在 `.env` 中填写：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

模型和 Base URL 可按需覆盖。不要把 API Key 写进代码或提交到仓库。

## 完整使用流程

推荐按下面顺序使用本工具：

1. 安装 Python 依赖。

```bash
pip install -r requirements.txt
```

2. 安装 FFmpeg，并确认命令可用。

```bash
ffmpeg -version
```

3. B站、YouTube 和通用 URL 均由项目的 yt-dlp Source 处理，无需额外平台 CLI。

4. 在项目 `.env` 中配置 `DEEPSEEK_API_KEY`；只转写时可使用 `--no-summary` 跳过云端调用。

5. 选择输入来源。

B站：

```bash
python -m src.main --url "B站链接" --backend deepseek --mode summary
```

YouTube / 其他公开视频：

```bash
python -m src.main --url "YouTube链接" --backend deepseek --mode tutorial
```

本地文件：

```bash
python -m src.main --file "input/test.mp4" --backend deepseek --mode summary
```

6. 选择分析模式。

```bash
python -m src.main --url "视频链接" --backend deepseek --mode summary
python -m src.main --url "视频链接" --backend deepseek --mode tutorial
python -m src.main --url "视频链接" --backend deepseek --mode viral
python -m src.main --url "视频链接" --backend deepseek --mode close-reading
```

7. `--comments` 仅为旧命令兼容保留；评论区功能已停用。

8. 如需 Obsidian 合并笔记，增加 `--export obsidian`。

```bash
python -m src.main --url "视频链接" --backend deepseek --mode tutorial --export obsidian
```

9. 如只想生成 `metadata.json` 和 `transcript.md`，不调用 LLM：

```bash
python -m src.main --url "视频链接" --no-summary
python -m src.main --file "input/test.mp4" --no-summary
```

每次运行都会在 `output/` 下生成一个独立目录。建议先检查 `metadata.json` 和 `transcript.md`，再查看 `summary.md`、`chapter_summary.md`、`highlight_notes.md` 以及对应模式报告。

## 处理视频链接

```bash
python -m src.main --url "https://www.bilibili.com/video/BVxxxx"
```

B站链接使用 DeepSeek 结构化分析：

```bash
python -m src.main --url "B站链接" --backend deepseek --mode summary
```

B站教程解析：

```bash
python -m src.main --url "B站链接" --backend deepseek --mode tutorial
```

B站内容结构拆解：

```bash
python -m src.main --url "B站链接" --backend deepseek --mode viral
```

原文细读：

```bash
python -m src.main --url "视频链接" --backend deepseek --mode close-reading
```

Obsidian 合并导出：

```bash
python -m src.main --url "视频链接" --backend deepseek --mode tutorial --export obsidian
```

YouTube 或其他 yt-dlp 支持的平台：

```bash
python -m src.main --url "YouTube链接" --backend deepseek --mode tutorial
```

指定语言：

```bash
python -m src.main --url "视频链接" --lang zh
```

显式指定 DeepSeek 后端：

```bash
python -m src.main --url "视频链接" --backend deepseek
```

只生成转写，不调用 LLM：

```bash
python -m src.main --url "视频链接" --no-summary
```

## 处理本地视频

把视频放到 `input/` 后运行：

```bash
python -m src.main --file "input/test.mp4"
```

本地视频摘要：

```bash
python -m src.main --file "input/test.mp4" --backend deepseek --mode summary
```

只生成转写：

```bash
python -m src.main --file "input/test.mp4" --no-summary
```

Windows 路径包含空格时请使用引号：

```bash
python -m src.main --file "C:\Users\me\Videos\test video.mp4" --no-summary
```

## 可视化 Web UI

也可以启动本地可视化页面，在浏览器中填写视频链接或本地文件路径：

```bash
python -m src.web --host 127.0.0.1 --port 5188
```

打开：

```text
http://127.0.0.1:5188
```

Web UI 会在后台调用同一套 CLI 流程，并在页面中显示任务状态、日志、输出目录和生成的 Markdown / JSON 文件链接。

## Codex Skill 使用方式

Skill 文件位于：

```text
.agents/skills/video-summary/SKILL.md
```

在 Codex 中可以这样提出任务：

```text
使用 video-summary skill，总结这个视频：https://www.bilibili.com/video/BVxxxx
```

或：

```text
使用 video-summary skill，总结本地视频 input/test.mp4
```

Skill 的执行逻辑：

1. Codex 进入 `video-summary-skill` 项目根目录；
2. 调用现有 CLI 生成 transcript，例如：

```bash
python -m src.main --url "视频链接" --no-summary
```

或：

```bash
python -m src.main --file "input/test.mp4" --no-summary
```

3. CLI 在 `output/` 下创建本次运行目录，并生成 `metadata.json` 与 `transcript.md`；
4. 如果存在 `DEEPSEEK_API_KEY`，CLI 会生成结构化 `analysis.json` 和对应 Markdown；
5. 如果没有 `DEEPSEEK_API_KEY`，字幕与时间轴仍会导出，分析状态记录为 `failed`。

这样可以保证没有 API Key 时也能完成完整的 `transcript.md -> summary.md` 工作流。

## 无字幕视频转写说明

当 `yt-dlp` 没有提取到可用字幕时，程序会自动进入：

1. FFmpeg 从视频中提取 16kHz 单声道 wav；
2. `faster-whisper` 使用配置中的模型转写；
3. 输出带时间戳的 `transcript.md`。

默认模型为 `small`，可在 `config.example.json` 中调整为 `medium` 等模型。模型越大，速度越慢，对显存和内存要求越高。

## 时间戳与原视频回链

`transcript.md` 会尽量保留每条字幕或转写片段的时间戳。对于公开视频链接，程序会把时间戳转换成可点击回链：

```md
- [00:02:10 - 00:02:16](原视频链接?t=130) 这里是字幕文本。
```

- B站链接使用 `?t=130` 或已有 query 时使用 `&t=130`。
- YouTube 链接使用 `?t=130s` 或已有 query 时使用 `&t=130s`。
- 本地文件或未知平台保留普通时间戳，不生成回链。

## 输出文件

每次运行会在 `output/` 下创建一个独立目录，包含：

- `index.md`
- `metadata.json`
- `manifest.json`
- `analysis.json`
- `timeline.json`
- `transcript.raw.jsonl`
- `transcript.grouped.md`
- `transcript.md`
- `source.md`
- `frames/`
- `audio/`
- `summary.md`
- `chapter_summary.md`，启用摘要且摘要后端可用时生成
- `highlight_notes.md`，启用摘要且摘要后端可用时生成
- `tutorial_report.md`，`--mode tutorial` 时生成
- `viral_analysis.md`，`--mode viral` 时生成
- `close_reading.md`，`--mode close-reading` 时生成
- `export_note.md`，`--export obsidian` 时生成，作为新`index.md`的兼容副本

历史输出中的`comments.json`、`comments.md`和`comment_insights.md`不会删除，但新 Pipeline 不再生成它们。

## 来源与 Provider

新 Pipeline 的来源层位于：

```text
src/sources/
├─ __init__.py
├─ base.py
├─ local_media.py
├─ ytdlp_source.py
└─ web_source.py
```

- `ytdlp_source.py`：统一处理 B站、YouTube 和其他 yt-dlp 视频，字幕优先、audio-only 兜底。
- `local_media.py`：处理本地视频和音频，复用 FFmpeg + faster-whisper。
- `web_source.py`：仅预留普通网页接口，本轮未实现正文抓取。
- `src/providers/`：提供 ASR/LLM 可替换边界；当前实现本地 Whisper 和现有 LLM 的 legacy 包装。

## 常见错误排查

- 视频链接无效：确认链接是公开视频，且当前网络可以访问。
- `yt-dlp` 无法提取字幕：程序会自动尝试下载音频并进入转写流程。
- 视频没有字幕：需要安装 FFmpeg，并安装 `faster-whisper` 依赖。
- FFmpeg 未安装：按上文安装 FFmpeg，并确认 `ffmpeg -version` 可运行。
- `faster-whisper` 转写失败：检查音频是否成功生成，或尝试更小的 Whisper 模型。
- 缺少 `DEEPSEEK_API_KEY`：CLI 保留 transcript 和知识包，并在 `analysis.json` 与 manifest 中记录可操作的失败原因。
- B站字幕获取失败：自动回退到 yt-dlp；如果仍无字幕，则进入 FFmpeg + faster-whisper 转写。
- `--comments`：该参数已停用，仅为旧命令兼容保留。
- 输出目录不存在：程序会自动创建 `output/`。
- Windows 路径包含空格：请给路径加英文双引号。
- 文件名包含非法字符：程序会自动清洗输出目录名称。

## 合规说明

本项目仅用于个人学习、研究、整理已授权或公开视频内容。不提供绕过付费、破解、去水印、批量搬运、侵权转载等功能。Cookie 只使用本机用户授权状态，不输出敏感 Cookie，不把账号凭据保存到项目仓库。请遵守视频平台服务条款、版权要求和当地法律法规。
