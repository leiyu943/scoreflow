@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在安装外部识别环境。首次需下载数 GB，请保持网络连接。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-runtime.ps1"
if errorlevel 1 (
 echo 安装未完成，请查看上方错误和 README 的安装指引。
 pause
 exit /b 1
)
echo 安装完成，请双击启动谱音.cmd。
pause
