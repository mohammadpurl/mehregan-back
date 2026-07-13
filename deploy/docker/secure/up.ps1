#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Build and start the hardened Mehreagan ERP stack.

.USAGE
  cd E:\ERP\Backend2
  .\deploy\docker\secure\up.ps1
#>

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $backendRoot

$compose = Join-Path $PSScriptRoot "docker-compose.yml"
$envFile = Join-Path $backendRoot ".env"

if (-not (Test-Path $envFile)) {
    throw "Missing .env — copy deploy\docker\secure\.env.example into Backend2\.env and set secrets + SERVER_IP"
}

# Ensure frontend dockerignore exists
$feIgnoreSrc = Join-Path $PSScriptRoot ".dockerignore.frontend"
$feRoot = Join-Path (Split-Path $backendRoot -Parent) "Frontend-Next3"
$feIgnoreDst = Join-Path $feRoot ".dockerignore"
if ((Test-Path $feRoot) -and (Test-Path $feIgnoreSrc) -and -not (Test-Path $feIgnoreDst)) {
    Copy-Item $feIgnoreSrc $feIgnoreDst
    Write-Host "Copied frontend .dockerignore -> $feIgnoreDst" -ForegroundColor Yellow
}

# Merge tip for backend dockerignore
$beIgnoreSrc = Join-Path $PSScriptRoot ".dockerignore.backend"
$beIgnoreDst = Join-Path $backendRoot ".dockerignore"
if ((Test-Path $beIgnoreSrc) -and -not (Test-Path $beIgnoreDst)) {
    Copy-Item $beIgnoreSrc $beIgnoreDst
    Write-Host "Copied backend .dockerignore -> $beIgnoreDst" -ForegroundColor Yellow
}

Write-Host "Stopping legacy stack (if any) to free port 80..." -ForegroundColor Cyan
docker compose -f (Join-Path $backendRoot "docker-compose.yml") down 2>$null

Write-Host "Building + starting secure stack..." -ForegroundColor Cyan
docker compose -f $compose --env-file $envFile up -d --build

Write-Host ""
Write-Host "Done. Check:" -ForegroundColor Green
Write-Host "  curl http://127.0.0.1/healthz"
Write-Host "  curl http://127.0.0.1/backend/health"
Write-Host "  .\deploy\docker\secure\security-check.ps1"
