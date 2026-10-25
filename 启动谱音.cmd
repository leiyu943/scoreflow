@echo off
chcp 65001 >nul
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
 echo 请先安装 Node.js 22.12 或更新的 LTS 版本，再重新运行。
 echo https://nodejs.org/en/download
 pause
 exit /b 1
)
node "%~dp0scripts\launch.cjs" %*
if errorlevel 1 pause
