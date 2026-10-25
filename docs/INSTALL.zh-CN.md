# ScoreFlow 安装与首次使用

[返回 README](../README.md)

适用版本：0.2.0 源码预览 / Windows x64。发布内容是文件和文件夹组成的源码目录，按下面步骤安装后运行，无需把数 GB 的依赖提交到仓库。

## 1 安装基础组件

1. 安装 [Node.js LTS，Windows x64](https://nodejs.org/en/download)，版本至少 22.12，保留安装器默认的 PATH 设置。
2. 安装 [Python 3.12，Windows x64](https://www.python.org/downloads/release/python-31210/)，保留 Python Launcher；推荐勾选 Add python.exe to PATH。Python 只用于后台，不负责桌面 UI。
3. 按显卡型号安装 [NVIDIA 官方驱动](https://www.nvidia.com/en-us/drivers/)，必要时重启。识别已在 RTX 3070 8 GB 验证；开始时需要约 5.5 GiB 空闲显存。

新开 PowerShell，检查：

```powershell
node --version
npm --version
py -3.12 --version
nvidia-smi
```

Node 至少 22.12，Python 必须是 3.12 的 x64 版。当前没有 CPU、AMD、Intel GPU 或其他操作系统的识别后端。

## 2 准备源码目录

把仓库下载或克隆到自己的位置，例如 `D:\Projects\ScoreFlow`。文件夹层级应如下，`README.md` 和 `package.json` 在同一层：

```text
ScoreFlow/
├─ 启动谱音.cmd
├─ 安装识别环境.cmd
├─ README.md
├─ package.json
├─ package-lock.json
├─ requirements-runtime.txt
├─ app/
├─ engine/
├─ scripts/
├─ docs/
├─ tests/
└─ licenses/
```

GitHub 自动提供的源码 ZIP 解压后也是这个目录。源码下载中没有 `ScoreFlow.exe` 是正常的；下面的启动入口会通过 Electron 打开桌面界面。

## 3 安装识别环境

双击 **安装识别环境.cmd**。它调用 `scripts/install-runtime.ps1` 和 `scripts/setup-runtime.py`，完成以下步骤：

1. 在源码目录之外创建 Python 3.12 虚拟环境。
2. 从 PyTorch 官方软件源安装 `torch==2.7.1`、`torchvision==0.22.1`，使用 CUDA 12.8 运行库。
3. 按 `requirements-runtime.txt` 安装 ONNX Runtime GPU 1.24.4、图像处理与 Tabbox 所需依赖。
4. 下载固定版本 HOMR 源码及三份 465 FP16 权重；下载固定版本 Tabbox 官方架构和公开 `best.pt`。
5. 下载 FluidSynth 2.6.0 和 GeneralUser GS 2.0.3，复制随源码提供的小型谱号校准资源。
6. 校验资源 SHA-256，检查 Python、CUDA 后端、模型与合成器；成功后写入本机的 `runtime.local.json`。

**默认环境目录：`%LOCALAPPDATA%\ScoreFlow\runtime`。** 大型依赖、模型、音色和下载缓存都位于此处。请至少预留 12 GB 空间；首次下载耗时取决于网络，不会只下载几百 KB 的源码。

想安装到 D 盘，可在源码目录打开 PowerShell，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-runtime.ps1 -RuntimeRoot 'D:\ScoreFlowRuntime'
```

这里的执行策略参数仅对这次脚本进程生效，不修改系统全局策略。安装使用独立虚拟环境，不要求将推理依赖安装进系统 Python。

### CUDA 应该怎么装

按本指南通过 PyTorch 官方 CUDA 12.8 wheel 安装时，通常不需要另外安装完整 CUDA Toolkit 或手动复制 cuDNN。驱动仍然需要自己安装，且必须支持当前运行库。[PyTorch 官方版本命令](https://pytorch.org/get-started/previous-versions/)、[ONNX Runtime 对 PyTorch DLL 的复用说明](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)

不要根据 `nvidia-smi` 的 CUDA Version 一栏就判断运行环境完整；那一栏表示驱动支持的 CUDA 能力。也不要只装 Toolkit，省略 PyTorch、ONNX Runtime 或模型文件。

### 手动安装命令

不使用双击入口时，在源码根目录运行以下命令即可执行同一套安装流程：

```powershell
py -3.12 .\scripts\setup-runtime.py --runtime-root 'D:\ScoreFlowRuntime'
```

脚本使用的核心 pip 命令如下。这里的 Python 是脚本创建的环境，不是全局 Python；完整脚本还负责模型、目录清单、音色和检查，因此只执行这两条 pip 命令不足以完成安装。

```powershell
& 'D:\ScoreFlowRuntime\python\Scripts\python.exe' -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
& 'D:\ScoreFlowRuntime\python\Scripts\python.exe' -m pip install -r .\requirements-runtime.txt
```

## 4 模型来源与版本

| 资源 | 来源 | 安装位置（相对于环境根目录） |
| --- | --- | --- |
| HOMR 源码 | [liebharc/homr](https://github.com/liebharc/homr)，固定提交 `6b5b518c964b0388335300a5702e4f6e404b9175` | `teacher_candidates/homr465/repo/` |
| HOMR 465 FP16 权重 | [官方 ONNX 下载页](https://github.com/liebharc/homr/releases/tag/onnx_checkpoints)，精确文件名见 `engine/model_assets.json` | HOMR 的 `homr/transformer/` 与 `homr/segmentation/` |
| Tabbox 公开权重 | [kk9293/guitar-tab-omr](https://huggingface.co/kk9293/guitar-tab-omr)，固定提交 `cf0aa64313e981e3c4337e322df6540958a55e1d` 的 `best.pt` | `models/tabbox-official.pt` |
| Tabbox 架构脚本 | [LIU9293/guitar-tab-omr](https://github.com/LIU9293/guitar-tab-omr)，固定提交 `3cd36084fda5433bb26cb3a3281f25e9e3ee0476` | `guitar-tab-omr/scripts/` |
| FluidSynth | [2.6.0 官方 Windows x64 版本](https://github.com/FluidSynth/fluidsynth/releases/tag/v2.6.0) | `audio/fluidsynth/`，含 EXE 和配套 DLL |
| GeneralUser GS | [作者的官方仓库](https://github.com/mrbumpy409/GeneralUser-GS)，2.0.3 | `audio/GeneralUser-GS.sf2` |

固定 URL 与校验值集中记录在 [runtime-downloads.json](../engine/runtime-downloads.json)。安装脚本下载外部资源，不将它们捆绑进源码；第三方资源保留各自许可。

公开 Tabbox 模型主要面向清晰、裁切好的单系统吉他六线谱。ScoreFlow 负责整页分行、多页连接与 MIDI 导出；六线谱仍在优化，输出应试听核对，不能将上游的渲染数据评估数字当成整个软件的扫描谱准确率。

### 配置已有的本地 Tabbox 调整版（可选）

默认公开安装已经包含可使用的六线谱模型。这一节只适用于持有原标注器调整版资源的人。

本地调整版与公开版都是 Tabbox，权重不同：公开版 SHA-256 为 `833a45752eb99cf525ec2744c20d93175540b487f162caa38e554fc3c7fb0f7e`；本地调整版登记为 `31c2863b78d09786dfdb9a25e9b0b8492766fcae1f94544e1ed49217a6e6ec08`。对应架构脚本也不同，不能只换权重不换代码。

提供匹配的 `best.pt`，以及包含 `guitar_omr_eval.py`、`guitar_omr_train.py`、`guitar_omr_dataset_smoke.py` 的脚本目录：

```powershell
py -3.12 .\scripts\setup-runtime.py --runtime-root 'D:\ScoreFlowRuntime' --tab-model 'D:\MyModels\best.pt' --tab-code 'D:\MyModels\scripts'
```

脚本会按本地调整版的固定哈希检查模型和三个脚本，再写入登记清单。此调整版权重暂无本项目公开下载地址；不影响普通用户安装默认的 Tabbox 公开版。

## 5 启动软件与检查环境

双击 **启动谱音.cmd**。首次自动执行 `npm ci` 下载 Electron，以后复用桌面依赖。先安装识别环境再启动即可进入识别；也可以先打开界面，但环境未安装前无法识别或采样试听。

安装成功后，源码根目录会出现只记录本机路径的 `runtime.local.json`，它已被 `.gitignore` 排除，不上传 GitHub。环境文件结构如下：

```text
D:\ScoreFlowRuntime\
├─ python\Scripts\python.exe
├─ python\Lib\site-packages\   PyTorch / CUDA / ONNX 等依赖
├─ model_registry.json
├─ models\tabbox-official.pt
├─ guitar-tab-omr\scripts\
├─ teacher_candidates\homr465\repo\
├─ teacher_refinement_v1_20261024\clef_model\
├─ gpu_runtime_v2\homr_weights_lock.json
├─ audio\GeneralUser-GS.sf2
├─ audio\fluidsynth\fluidsynth.exe  及配套 DLL
└─ .downloads\                 安装下载缓存
```

重新检查已有环境，不安装或下载：

```powershell
py -3.12 .\scripts\setup-runtime.py --runtime-root 'D:\ScoreFlowRuntime' --check --require-tab
```

此检查验证关键文件、权重哈希、依赖版本、CUDA 是否可用及合成器能否启动。完整识别仍需在软件中用一张清晰谱面测试；显存保护在实际推理前执行。

复用旧版已验证的完整环境时，也可在界面左下角选择 **直接包含 `model_registry.json` 的根目录**，例如 `D:\ScoreFlowRuntime`，不要选下面的 `python` 或 `models`。旧环境的独立 Python 与分目录依赖布局仍兼容。

环境查找顺序：`SCOREFLOW_RUNTIME_ROOT` 环境变量 → 用户保存的配置 → 源码/应用旁的 `runtime.local.json` → 同目录 `runtime`。如果终端设置过环境变量，它会覆盖其他选择；移动环境后应重新选择。新安装使用标准 Python 虚拟环境，**不要移动环境或卸载其基础 Python**；换路径时在新位置重新安装。

## 用三页谱完成第一次识别

1. 点击 **导入多页**，多选三张谱面。支持 PNG、JPG/JPEG、WebP、BMP。
2. 文件名按自然数字顺序排序，如 `page-1`、`page-2`、`page-10`。在页码列表检查实际顺序，用左右箭头调整。
3. 选择模式：
   - **自动**：五线谱、纯六线谱、混合页自动路由；混合页优先五线谱。
   - **五线谱**：使用已调整和校正的五线谱链路。
   - **六线谱**：可读取纯六线谱或混合页中的六线谱，仍在优化。
4. 拍号可以自动识别，也可以手动指定。点击 **开始识别并保存 MIDI**，程序按顺序处理各页。
5. 识别成功后，卷帘显示整曲。开启 **跟随播放**，播放会自动翻页；点击第三页音符会跳到整曲中对应位置。
6. 在底部 **音色** 选择吉他、钢琴等采样音色。首次切换会短暂本地渲染；调速会重新渲染，以保持音高。
7. 点击 **导出 MIDI** 保存完整曲子，或另存结构兼容时的 MusicXML。

追加、移除和重新排序不会改写原图。当前曲目内的已完成页可复用；取消或失败后再次开始，会按输入和设置检查可复用结果。当前没有可重新打开的项目格式，退出前请导出需要的曲目。

## 文件保存位置

点击左侧 **识别结果** 可以打开结果目录。默认路径通常为：

```text
%APPDATA%\ScoreFlow\results\piece-…\complete\
  score.mid         完整曲目
  score.musicxml    结构兼容时生成
  result.json       页序、音符、坐标引用和复核信息
```

各页中间结果位于相应识别任务目录；缓存复用时，可能引用此前任务中已保存的页。`%APPDATA%\ScoreFlow\audio-cache` 是采样试听缓存，不是最终 MIDI。单纯移动或删除便携程序目录不会自动删除这些用户数据。

## 常见问题

| 情况 | 处理方法 |
| --- | --- |
| 找不到 EXE，只有源码 | 本仓库按源码发布，先安装基础组件，再运行两个 CMD 入口 |
| 双击启动后下载失败或缺少桌面文件 | 检查 Node 版本和网络，在源码目录运行 npm ci 后重试 |
| 提示环境不完整 | 选择含 `model_registry.json` 的根目录，并检查模型和依赖是否齐全 |
| CUDA 不可用或显存不足 | 检查驱动、`nvidia-smi` 与空闲显存；当前不自动回退 CPU |
| 权重校验失败 | 获取与该版本清单匹配的权重；不要修改校验值来绕过检查 |
| 音色加载失败或无声 | 检查 `runtime/audio` 的 SF2、FluidSynth 和动态库，以及系统音量和输出设备 |
| 混合页没有读取六线谱 | 自动模式本来优先五线谱；选择“六线谱”再识别 |
| 某页失败 | 处理或移除有问题的页后重试；不要把缺页结果作为完整曲目 |
| 合并 MusicXML 不可用 | 页间声部数量不同；完整 MIDI 仍可导出，各页 XML 仍保留 |
| 关闭后没有恢复页列表 | 本版没有项目恢复功能；自动保存的 MIDI 仍在结果目录，可在音乐软件中打开 |

如果是真实 GPU 故障导致后续任务被保护锁阻止，先查看日志并处理显卡、驱动、温度或内存问题。维护者可在确认状态恢复后复位保护记录；不要把复位当作修复硬件。以下路径需替换成实际源码与运行环境位置：

```powershell
$env:SCOREFLOW_STATE_ROOT = Join-Path $env:APPDATA 'ScoreFlow\gpu-state'
& 'D:\ScoreFlowRuntime\python\Scripts\python.exe' 'D:\Projects\ScoreFlow\engine\gpu_guard.py' status
# 确认日志与设备状态后，才手动运行：
# & 'D:\ScoreFlowRuntime\python\Scripts\python.exe' 'D:\Projects\ScoreFlow\engine\gpu_guard.py' acknowledge
```


## 开发与构建

手动启动界面：

```powershell
npm ci
npm start
```

手动指定识别环境：

```powershell
$env:SCOREFLOW_RUNTIME_ROOT = 'D:\ScoreFlowRuntime'
npm start
```

无需模型的验证和桌面构建：

```powershell
npm test
python tests/engine_test.py
python tests/assemble_test.py
python tests/setup_runtime_test.py
npm run build
```

Python 两套单元测试只用标准库，可用 3.11/3.12；真实识别环境固定 3.12。`npm run build` 在源码目录同级生成 `ScoreFlow-Windows-x64`，不复制模型与依赖。关闭已有应用再构建；运行生成的 EXE 时，在界面选择同一份外部识别环境即可。

## 网络与安装失败

- 下载失败：查看报错对应的官方地址，确认能访问 GitHub、Hugging Face、PyPI、PyTorch 软件源和 Electron 下载源后重试。脚本复用已完成且校验通过的模型文件。
- 需要代理时，按自己的网络配置临时设置 `HTTPS_PROXY` / `HTTP_PROXY` 后，从同一终端执行安装命令；仓库不内置私人代理地址。
- Python 版本错误：使用 `py -3.12 --version` 检查，不要用 3.11、3.13 或 32 位 Python 安装识别环境。
- 缺少 Visual C++ DLL：安装 [Microsoft 官方 x64 运行库](https://aka.ms/vs/17/release/vc_redist.x64.exe)，再重新检查。
- `CUDA 不可用`：先检查 `nvidia-smi` 和驱动，确认是 NVIDIA 显卡，再检查安装日志；当前不会自动回退 CPU。
- 源码上传：使用干净的上传目录，或通过 Git 的忽略规则排除 `node_modules`、模型、运行环境和 `runtime.local.json`；浏览器拖拽上传不会替你执行 `.gitignore` 过滤。

安装入口不发送谱面，不下载训练集，不执行训练，不自动上传模型。
