$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'serve.py'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
# Match this installation's absolute entrypoint and Python environment only.
$owned = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($entry) -and $_.CommandLine.Contains($python)
})
if (!$owned.Count) { Write-Host 'RiverGuard is already stopped for this folder.'; exit 0 }
$owned | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
Write-Host 'RiverGuard stopped. Saved readings and chats remain. An unfinished reply can be retried after restarting.'
