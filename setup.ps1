$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.txt"

if (-not (Test-Path -LiteralPath $venvPython)) {
    & python -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the project virtual environment."
    }
}

& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Could not install project dependencies into .venv."
}

Write-Output "Project environment is ready. Run .\run.ps1 to start the app."
