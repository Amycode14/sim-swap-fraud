$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Install Python 3.12 or newer first." }
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& .\.venv\Scripts\python.exe scripts/init_demo.py
if ($LASTEXITCODE -ne 0) { throw "Configuration failed." }
Write-Host "Your local demo access token (valid two hours):"
& .\.venv\Scripts\python.exe scripts/issue_demo_token.py
Write-Host "Open http://127.0.0.1:8000 and paste this token. Ctrl+C stops the server."
& .\.venv\Scripts\python.exe scripts/run.py
