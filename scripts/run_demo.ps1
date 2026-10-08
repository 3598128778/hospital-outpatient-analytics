$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
}
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& ./.venv/Scripts/python.exe -m hospital.pipeline --generate
if ($LASTEXITCODE -ne 0) { throw 'Pipeline failed.' }
& ./.venv/Scripts/python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& ./.venv/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1
