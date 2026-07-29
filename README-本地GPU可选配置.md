# Viewledge 本地 GPU 可选配置

本地 GPU 转写是高级可选能力，不是 Viewledge 启动条件。普通用户优先使用平台字幕；没有字幕时可选择云端快速转写或安装小模型后使用本地 CPU。

基础发行包不会安装 NVIDIA CUDA、cuDNN、cuBLAS，也不会自动下载语音模型。若你已经维护好兼容的 NVIDIA 驱动和本地 GPU 运行环境，可把模型扩展包解压到 Viewledge 根目录，再从“新总结”刷新能力检测。

模型目录应为：

```text
models/
└─ faster-whisper-small/
   ├─ config.json
   ├─ model.bin
   └─ tokenizer.json
```

能力检测显示本地 GPU 不可用时，仍可选择本地 CPU。运行期间 GPU 初始化、加载或转写失败时，现有稳定回退逻辑会复用已提取音频并尝试本地 CPU，不会重新下载视频。

诊断人员可使用本机自备且被 Git 忽略的 `start_dev.bat` 查看非敏感技术信息。该文件不属于公开发行包。
