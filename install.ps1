$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
