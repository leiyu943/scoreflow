# 第三方组件与许可说明

谱音的应用源码和从原项目提取的代码采用 AGPL-3.0-only。各项依赖、模型及音色保留自己的许可，本说明不改变外部资源的授权。

- **HOMR**：来源为 [liebharc/homr](https://github.com/liebharc/homr)，本地固定版本声明 AGPL-3.0。`engine/vendor/music_xml_generator.py` 保留原项目对反复起点的修正。许可全文见 `engine/vendor/HOMR-LICENSE` 和根目录 `LICENSE`，提取来源与原文件哈希见 `engine/PROVENANCE.json`。
- **HOMR 的 ONNX 权重**：来自 [官方模型发布页](https://github.com/liebharc/homr/releases/tag/onnx_checkpoints)，遵循上游模型条款。`runtime/gpu_runtime_v2/homr_weights_lock.json` 记录三份模型的精确哈希。
- **Guitar Tab OMR / Tabbox 六线谱模型**：来源为 [模型主页](https://huggingface.co/kk9293/guitar-tab-omr)。默认安装器从上游下载固定版本公开权重与推理脚本，不捆绑分发。原项目另提供本地适配权重和配套推理脚本；本次检查的本地外部脚本仓库未附 LICENSE 文件，不能由谱音重新授权其代码或权重。公开源码包不含这套外部运行环境；公开捆绑分发前，应向资源所有者确认适用授权。
- **Electron**：采用 MIT 许可。桌面包保留 `ELECTRON-LICENSE`、`LICENSES.chromium.html` 等上游声明；应用自身许可保存在根目录 `LICENSE`。
- **Python**：采用 PSF 许可，便携运行环境保留原解释器许可文件。
- **PyTorch、torchvision、ONNX Runtime、OpenCV、NumPy、Pillow 等依赖**：分别保留上游许可，具体版本和文件见运行环境中的 `.dist-info` 元数据与许可文件。
- **NVIDIA CUDA / cuDNN**：遵循 NVIDIA 适用的软件条款，不属于应用 AGPL 许可下的开源代码。
- **GeneralUser GS 2.0.3**：S. Christian Collins 提供的采样音色库，来源为 [作者主页](https://schristiancollins.com/generaluser)。运行环境保留未修改的音色库和 `audio/GeneralUser-GS-LICENSE.txt`。其自定义许可独立于应用许可。
- **FluidSynth 2.6.0**：采用 LGPL-2.1，来源及对应源码见 [官方版本](https://github.com/FluidSynth/fluidsynth/tree/v2.6.0)。采样渲染使用独立可执行文件和动态库，未修改合成器二进制；许可保存在 `audio/FLUIDSYNTH-LICENSE.txt`。配套 SDL3 与 libsndfile 也保留自己的许可，来源分别为 [SDL](https://github.com/libsdl-org/SDL) 和 [libsndfile](https://github.com/libsndfile/libsndfile)。
- **内置《晨间小调》**：为本应用制作的原创播放示例。应用和公开源码包均不包含第三方乐谱训练数据集。

界面和使用文档采用中文。第三方许可证保留上游原文，以便准确保留授权条件与来源。
