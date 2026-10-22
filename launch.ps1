$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run Setup RiverGuard.cmd first.' }
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\dist\index.html'))) {
    throw 'The built interface is missing. Extract the complete RiverGuard ZIP again.'
}
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCommand -and !(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $ollamaCommand.Source -ArgumentList 'serve' -WindowStyle Hidden
}
& $python (Join-Path $PSScriptRoot 'serve.py')
if ($LASTEXITCODE -ne 0) { throw 'RiverGuard stopped. Read the startup error above, then try again.' }
