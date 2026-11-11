$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Project environment not found. Run .\setup.ps1 first."
}

$appPath = Join-Path $PSScriptRoot "app.py"
& $venvPython $appPath @args
exit $LASTEXITCODE
