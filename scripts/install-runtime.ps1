param([string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'ScoreFlow\runtime'))
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidates += @{ Exe = 'py'; Prefix = @('-3.12') }
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    $candidates += @{ Exe = 'python'; Prefix = @() }
}
$condaPython = Join-Path $env:USERPROFILE 'anaconda3\python.exe'
if (Test-Path -LiteralPath $condaPython) {
    $candidates += @{ Exe = $condaPython; Prefix = @() }
}
foreach ($candidate in $candidates) {
    $program = $candidate.Exe
    $prefix = $candidate.Prefix
    try {
        & $program @prefix -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)' 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
    } catch { continue }
    & $program @prefix (Join-Path $PSScriptRoot 'setup-runtime.py') --runtime-root $RuntimeRoot
    exit $LASTEXITCODE
}
Write-Host '未找到 Windows x64 Python 3.12。请先安装，安装时保留 Python Launcher。'
Write-Host 'https://www.python.org/downloads/release/python-31210/'
exit 1
