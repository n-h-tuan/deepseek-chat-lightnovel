$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python was not found on PATH."
}

$chunkerPath = Join-Path $PSScriptRoot "chunk.py"
& $python.Source $chunkerPath @args
exit $LASTEXITCODE
