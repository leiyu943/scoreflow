'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const [major, minor] = process.versions.node.split('.').map(Number);
if (major < 22 || (major === 22 && minor < 12)) {
  console.error('需要 Node.js 22.12 或更新版本，请从 https://nodejs.org/en/download 安装 LTS 版本。');
  process.exit(1);
}
const exe = path.join(root, 'node_modules/electron/dist/electron.exe');
if (!fs.existsSync(exe)) {
  console.log('首次启动：正在下载桌面界面依赖，请保持网络连接。');
  const install = spawnSync('cmd.exe', ['/d', '/s', '/c', 'npm ci'], { cwd: root, stdio: 'inherit' });
  if (install.status !== 0 || !fs.existsSync(exe)) {
    console.error('桌面依赖安装失败。请检查上方网络错误，再重新运行启动入口。');
    process.exit(install.status || 1);
  }
}
if (!process.env.SCOREFLOW_RUNTIME_ROOT && !fs.existsSync(path.join(root, 'runtime.local.json'))) {
  console.log('识别环境尚未配置：请另行运行“安装识别环境.cmd”。界面可以先打开。');
}
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const result = spawnSync(exe, [root, ...process.argv.slice(2)], { cwd: root, env, stdio: 'inherit' });
if (result.error) console.error('启动失败：' + result.error.message);
process.exit(result.status ?? 1);
