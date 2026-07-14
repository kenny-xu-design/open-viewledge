# CODEX_TASKS

## 规则
- 每轮只做一个任务。
- 测试通过才提交。
- 不允许删除已有核心流程。
- 不允许加入与 video-summary-skill 无关的功能。
- 不允许一次性大重构。

## 待办任务
- [x] 检查并修复 Ollama qwen3:8b 后端，确保不需要 OPENAI_API_KEY。
- [x] 增加 --mode summary / tutorial / viral / close-reading 参数。
- [x] 新增 tutorial_prompt.md，并输出 tutorial_report.md。
- [x] 新增 viral_prompt.md，并输出 viral_analysis.md。
- [x] 新增 chapter_prompt.md，并输出 chapter_summary.md。
- [x] 新增 highlight_prompt.md，并输出 highlight_notes.md。
- [x] 新增 close_reading_prompt.md，并输出 close_reading.md。
- [x] 新增 export_note.md，支持 Obsidian 导出。
- [x] 增强 transcript.md 时间戳和原视频回链。
- [x] README 增加完整使用流程。
- [x] 增加 tests/ 目录，做基础单元测试。
- [x] 增加 Codex Skill 的 .agents/skills/video-summary/SKILL.md。
