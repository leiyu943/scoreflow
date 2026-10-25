# 独立运行环境约定

桌面界面和识别源码可以独立发布。模型和原生依赖位于单独的 `runtime` 目录，通过 `SCOREFLOW_RUNTIME_ROOT` 或界面中的“配置模型运行环境”选择，不依赖标注器 UI。

公开源码的默认安装入口是 `安装识别环境.cmd`，详细命令见 [中文安装指引](docs/INSTALL.zh-CN.md)。默认运行根目录为 `%LOCALAPPDATA%\ScoreFlow\runtime`，也可通过 `scripts/install-runtime.ps1 -RuntimeRoot 'D:\ScoreFlowRuntime'` 自定义。安装器新建 `python/Scripts/python.exe` 和 `python/Lib/site-packages`，通过官方软件源下载依赖，不把第三方二进制放进源码。

默认六线谱使用 Tabbox 公开权重（`models/tabbox-official.pt`）与固定版本上游脚本。原标注器的本地调整版仍可选用，权重与三个脚本必须一同匹配；安装器按不同配置写入 `model_registry.json`。下载清单见 `engine/runtime-downloads.json`。`engine/assets/clef_model` 只包含约 3.4 KB 的校准参数与模板，随校正规则一起发布。

以下表格还记录原独立运行环境的兼容路径；新安装不需要人为创建所有旧依赖目录。

0.2.0 新增多页串行识别与整曲合并，继续使用同一份模型运行环境，不复制模型、不并行启动 GPU 推理。`engine/assemble.py` 只使用 Python 标准库和原有 MIDI 核心，合并不依赖 GPU。可通过 `python engine/assemble.py pages.json --output complete` 独立调用；清单格式为 `{"pages":[{"id":"page1","name":"第一页.png","result":"D:/results/page1/result.json"}]}`。

| 路径 | 用途 |
| --- | --- |
| `python/Scripts/python.exe`、`python/Lib/site-packages` | 新安装的 Python 3.12 虚拟环境与依赖，路径不可直接移动 |
| `python/python.exe` | 独立 Python 3.12，不是指回原机器的 venv 启动器 |
| `gpu_env/Lib/site-packages` | 已验证的 PyTorch 2.7.1 + CUDA 12.8 推理依赖 |
| `gpu_runtime_v2/pydeps` | 固定版本 ONNX Runtime CUDA、OpenCV 等依赖 |
| `teacher_candidates/homr465/repo` | HOMR 源码及三份 FP16 ONNX 模型，保留上游许可 |
| `teacher_candidates/homr465/pydeps` | HOMR 补充依赖 |
| `teacher_refinement_v1_20261024/clef_model` | 原有像素谱号校正资源 |
| `smt_pydeps`、`oemer_env/Lib/site-packages` | TAB 模型依赖；不启动 OEMER 模型 |
| `guitar-tab-omr/scripts` | 外部 TAB 模型的架构和解码实现，接口由 `engine/tabbox_batch_worker.py` 调用 |
| `models/best.pt` | 已部署的六线谱适配权重 |
| `model_registry.json` | 相对权重路径与 SHA-256 |
| `gpu_runtime_v2/homr_weights_lock.json` | 三份 HOMR 权重的相对路径与 SHA-256 |
| `audio/fluidsynth/` | FluidSynth 2.6.0 可执行文件及动态库 |
| `audio/GeneralUser-GS.sf2` | GeneralUser GS 2.0.3 采样音色库 |

本项目的 `engine/model_assets.json` 记录已验证的权重哈希，`engine/runtime-dependencies.json` 记录实际采用的包版本。组装现有标注器资源可以运行 `scripts/pack-runtime.py`；也可以按此约定组装自己的运行环境或提供独立下载包。公开的源码目录不携带外部模型权重、TAB 架构代码、已安装依赖或训练数据；安装时从上游下载。

音色库来源：[S. Christian Collins / GeneralUser GS](https://schristiancollins.com/generaluser)。原生合成器来源：[FluidSynth 2.6.0](https://github.com/FluidSynth/fluidsynth/tree/v2.6.0)。音色库和合成器各自的许可证保存在 `licenses/`，运行环境也附有对应副本。替换音色库时需维持 GM 音色号对应关系。

当前完整 Windows x64 目录约 7.13 GiB，主要体积来自 PyTorch/CUDA 动态库。识别需 NVIDIA CUDA 显卡；本次验证设备是 RTX 3070 8 GB。继承的 GPU 保护在启动时要求约 5.5 GB 空闲显存。仅查看与播放内置示例不需要 GPU 推理，但需要采样音色资源。不同显卡、驱动和扫描版式的表现仍需各自验证。
