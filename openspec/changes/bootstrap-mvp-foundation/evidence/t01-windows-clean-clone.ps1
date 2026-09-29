# T01 (Windows): follow the README guide from a fresh clone with empty uv/npm caches and
# an isolated Compose project, then remove only that project's containers and volumes.
# Usage (from the repository root):
#   powershell -NoProfile -ExecutionPolicy Bypass -File openspec/changes/bootstrap-mvp-foundation/evidence/t01-windows-clean-clone.ps1
param([string]$ApiPort = "18081")
$ErrorActionPreference = "Continue"
$src = (Resolve-Path "$PSScriptRoot\..\..\..\..").Path
$base = Join-Path $env:TEMP "m0-clean-win"
if (Test-Path $base) { Remove-Item -Recurse -Force $base }
New-Item -ItemType Directory $base | Out-Null
$env:UV_CACHE_DIR = "$base\uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$base\uv-python"
$env:npm_config_cache = "$base\npm-cache"
$env:COMPOSE_PROJECT_NAME = "recon-m0-clean"

function Step($name, [scriptblock]$cmd) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & $cmd 2>&1 | ForEach-Object { "$_" }
    "### STEP $name exit=$LASTEXITCODE seconds=$([math]::Round($sw.Elapsed.TotalSeconds,1))"
}

Step "git clone" { git clone --quiet $src "$base\repo" }
Set-Location "$base\repo"
"commit: $(git rev-parse --short HEAD)"
Step "uv sync --locked" { uv sync --locked }
Step "python version" { uv run python -c "import sys, platform; print(sys.version, platform.platform())" }
Step "npm ci" { npm ci --no-audit --no-fund }
Step "copy env" { Copy-Item .env.example .env; (Get-Content .env) -replace '^API_HOST_PORT=.*', "API_HOST_PORT=$ApiPort" | Set-Content .env -Encoding ascii }
Step "doctor" { uv run python scripts/doctor.py }
Step "gate static" { uv run python scripts/gate.py static }
Step "gate smoke" { uv run python scripts/gate.py smoke }
New-Item -ItemType Directory -Force "$src\.smoke" | Out-Null
Get-ChildItem .smoke -Filter *.json | ForEach-Object { Copy-Item $_.FullName "$src\.smoke\clean-windows-$($_.Name)" }
Step "teardown clean project (own volumes)" { docker compose --profile smoke down --volumes }
