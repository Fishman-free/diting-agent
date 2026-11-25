# 在桌面创建「谛听 Diting」启动图标（幂等，重跑覆盖）。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\make_desktop_shortcut.ps1
$repo = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop '谛听 Diting.lnk'

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = Join-Path $repo 'scripts\launch_diting.bat'
$lnk.WorkingDirectory = $repo
$lnk.IconLocation = (Join-Path $repo 'assets\diting.ico') + ',0'
$lnk.Description = '谛听 Diting Agent — 听万物 · 辨真伪'
$lnk.Save()

Write-Host "[谛听] 桌面图标已创建：$lnkPath"
