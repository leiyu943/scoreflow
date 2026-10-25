# ScoreFlow 的 GitHub 发布指引

[返回 README](../README.md)

本指南对应 0.2.0 预览版。**本次按干净的源码目录发布，模型和运行依赖从上游单独下载。** 当前源码与约 7.13 GiB 的完整运行目录应分开管理，不能把整个工作目录上传为代码。

## 1 先分清三件事

| 内容 | 放哪里 | 当前操作 |
| --- | --- | --- |
| 应用源码、文档、图标、许可证 | GitHub 仓库 | 上传干净源码目录内的文件与子目录 |
| 模型与推理依赖 | README 及下载清单中的上游地址 | 安装脚本下载到独立环境，不提交已安装文件 |
| 训练集、用户谱面、私人路径、日志、令牌 | 不属于公开源码包 | 不上传 |

本地检查尚未确认外部六线谱架构代码和适配权重的完整再分发授权。本项目的 AGPL 许可证不能代替外部组件的授权；当前源码 ZIP 已排除模型运行环境。详情见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。这不妨碍先公开已经准备好的应用源码和接口。

## 2 创建仓库

在 GitHub 新建仓库，建议使用：

- 名称：`ScoreFlow`。
- 描述：`将多页吉他乐谱连接成完整 MIDI，支持点谱定位播放和自动翻页。`
- 可见性：准备好公开源码后选择 Public；也可以先建 Private 自查，再手动改为 Public。
- **不要勾选自动创建 README、.gitignore 或 License**，这些文件在源码里已经准备好。不要另外选择 MIT 来覆盖现有 AGPL 许可。

建议 Topics：`optical-music-recognition`、`midi`、`musicxml`、`guitar`、`tablature`、`electron`、`windows`。

GitHub 官方也建议导入已有项目时先创建空仓库，避免与本地初始提交冲突。[导入本地源码](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

## 3 上传源码

### 推荐方式 使用 Git

1. 进入干净的源码目录，确认 `package.json` 和两个 CMD 启动入口位于根目录。不要在 Windows 磁盘根目录、整个项目工作区或完整运行包目录执行下面的命令。
2. 确认 `git --version` 可运行。将命令中的工作路径和 `YOUR_GITHUB_USERNAME` 换成自己的；若仓库名不是 `ScoreFlow`，也要改远程地址。
3. 在 PowerShell 中执行：

```powershell
Set-Location 'D:\Projects\ScoreFlow'
git init -b main
git add .
git status --short
git diff --cached --stat
```

检查待提交列表应是 `app/`、`engine/`、`scripts/`、`tests/`、`docs/`、`licenses/` 和根目录文档；不应出现 `runtime/`、`node_modules/`、`dist/`、大模型或私人文件。然后执行：

```powershell
git commit -m 'Initial source preview v0.2.0'
git remote add origin 'https://github.com/YOUR_GITHUB_USERNAME/ScoreFlow.git'
git push -u origin main
```

如果 Git 提示身份未设置，先在这个仓库中设置你自己的提交姓名和邮箱，再重新提交：

```powershell
git config user.name 'YOUR_NAME'
git config user.email 'YOUR_EMAIL_OR_GITHUB_NOREPLY_EMAIL'
```

首次推送需要 GitHub 身份认证，请按官方认证流程完成，不要把登录令牌放进源码或远程 URL。这里的命令是供你操作的发布步骤，不会替你创建或上传仓库。

### 不用命令行的方式

创建空仓库后，使用 GitHub 网页的 **Add file → Upload files**，上传源码解压后的内容，而不是只上传一个源码 ZIP。确保 `README.md` 和 `.gitignore` 位于仓库根目录，文件夹结构保持完整。提交后，首页应直接显示中文 README，并能打开中文安装指引。

GitHub 网页上传单文件上限为 25 MiB；普通 Git 仓库会阻止大于 100 MiB 的文件。当前干净源码很小，模型运行环境不应走这个通道。[官方文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

## 4 创建源码预览 Release

进入仓库的 **Releases → Draft a new release**：

1. 新建标签 `v0.2.0`，目标选择这次源码提交所在的 `main` 分支。
2. 标题填写 `ScoreFlow v0.2.0 预览版`。
3. 将 [中文发布文案](RELEASE_NOTES_v0.2.0.md) 复制到描述中。该文案按“先发布源码预览”准备，明确说明源码不含运行环境。
4. 勾选 **This is a pre-release**。先保存草稿，核对内容和附件，最后再发布。

发布后 GitHub 会按标签自动提供 Source code ZIP/TAR。可以另附自己整理的源码 ZIP，但不要把 GitHub 的自动源码包描述为可直接运行的 Windows 软件。[官方 Release 说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)、[创建 Release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

## 5 本次按目录发布，不压缩完整环境

上传源码目录中的文件和子文件夹，保持层级；仓库根目录应直接包含 `README.md`、`package.json`、`启动谱音.cmd` 和 `安装识别环境.cmd`。不要将源码 ZIP 当作唯一代码文件上传。

PyTorch、CUDA 运行库、ONNX Runtime、HOMR、Tabbox 权重和音色从 README 指向的上游地址下载，安装器将它们放在用户电脑的独立环境目录。无需把整套环境压缩或上传到代码仓库。

README 已提供普通用户的路径：安装 Node.js / Python / 显卡驱动 → 双击“安装识别环境.cmd” → 双击“启动谱音.cmd”。下载清单为 `engine/runtime-downloads.json`，Python 依赖清单为 `requirements-runtime.txt`。

公开安装默认使用 Tabbox 公开权重，和原标注器本地调整版权重分开记录。若后续发布本地调整版，另补其真实地址、精确哈希及对应脚本，不覆盖公开版的版本说明。

## 6 发布前最后核对

- 仓库首页能打开中文 README，图片和安装文档链接有效。
- 页面准确写明“五线谱链路已优化 / 六线谱持续优化”，没有未经验证的准确率数字。
- 当前下载类型写清楚：源码预览，还是完整便携运行包。
- 仓库里没有 `runtime`、训练集、用户乐谱、`node_modules` 或凭据。
- 保留原有 AGPL、派生代码来源、外部组件条款和音色许可；完整包与对应源代码一致。
- 两个 CMD 启动入口、依赖清单和固定下载清单齐全；运行环境与 node_modules 不在上传目录。

发布后可以把演示视频地址放在 README 的开头附近，再将 GitHub 仓库与下载说明放进视频简介。当前没有真实仓库 URL，因此文档没有伪造下载链接；创建仓库后使用它自己的 Releases 页面。

GitHub 文件限制核对日期：2026-10-25。后续版本发布前请重新查看文中官方文档。
