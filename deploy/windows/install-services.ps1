#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Install Mehreagan ERP Windows services (API, RabbitMQ consumer, Next.js) via NSSM.

.PREREQUISITES
  - NSSM: https://nssm.cc/download  (place nssm.exe in PATH or set $NssmPath below)
  - Python venv + pip install -r requirements.txt + pip install pika
  - npm ci && npm run build in frontend folder
  - PostgreSQL + RabbitMQ running on localhost
  - backend .env configured (see backend.env.example)

.USAGE
  1. Edit $Config below (paths, domain is informational only)
  2. Run in elevated PowerShell:
       Set-ExecutionPolicy -Scope Process Bypass
       .\install-services.ps1
  3. Copy deploy\windows\web.config to IIS site folder
#>

$ErrorActionPreference = "Stop"

$Config = @{
    BackendRoot   = "C:\apps\mehreagan\Backend2"
    FrontendRoot  = "C:\apps\mehreagan\Frontend-Next3\erp"
    IisSiteRoot   = "C:\inetpub\mehreagan-erp"
    ServiceUser   = "NT AUTHORITY\NETWORK SERVICE"
    ApiHost       = "127.0.0.1"
    ApiPort       = 8000
    FrontendPort  = 3000
    ApiWorkers    = 2
    NssmPath      = "nssm"
}

function Test-Command($Name) {
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-Path($Path, $Label) {
    if (-not (Test-Path $Path)) {
        throw "Missing $Label`: $Path"
    }
}

Write-Host "=== Mehreagan ERP — Windows service installer ===" -ForegroundColor Cyan

Assert-Path $Config.BackendRoot "BackendRoot"
Assert-Path $Config.FrontendRoot "FrontendRoot"
Assert-Path (Join-Path $Config.BackendRoot "venv\Scripts\uvicorn.exe") "uvicorn (run: python -m venv venv; pip install -r requirements.txt)"
Assert-Path (Join-Path $Config.BackendRoot ".env") "backend .env (copy from deploy\windows\backend.env.example)"
Assert-Path (Join-Path $Config.FrontendRoot ".next") "frontend build (run: npm run build)"

if (-not (Test-Command $Config.NssmPath)) {
    throw "NSSM not found. Download from https://nssm.cc and set `$Config.NssmPath"
}

$uvicorn = Join-Path $Config.BackendRoot "venv\Scripts\uvicorn.exe"
$python  = Join-Path $Config.BackendRoot "venv\Scripts\python.exe"
$npmCmd  = Join-Path $env:ProgramFiles "nodejs\npm.cmd"
if (-not (Test-Path $npmCmd)) {
    $npmCmd = "npm.cmd"
}

function Install-NssmService {
    param(
        [string]$Name,
        [string]$App,
        [string]$AppDirectory,
        [string[]]$AppParameters = @(),
        [hashtable]$EnvExtra = @{}
    )

    $existing = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Stopping existing service: $Name" -ForegroundColor Yellow
        & $Config.NssmPath stop $Name 2>$null
        Start-Sleep -Seconds 2
        & $Config.NssmPath remove $Name confirm
        Start-Sleep -Seconds 1
    }

    Write-Host "Installing service: $Name" -ForegroundColor Green
    & $Config.NssmPath install $Name $App @AppParameters
    & $Config.NssmPath set $Name AppDirectory $AppDirectory
    & $Config.NssmPath set $Name Start SERVICE_AUTO_START
    & $Config.NssmPath set $Name ObjectName $Config.ServiceUser
    & $Config.NssmPath set $Name AppStdout (Join-Path $AppDirectory "logs\$Name.stdout.log")
    & $Config.NssmPath set $Name AppStderr (Join-Path $AppDirectory "logs\$Name.stderr.log")
    & $Config.NssmPath set $Name AppRotateFiles 1
    & $Config.NssmPath set $Name AppRotateBytes 10485760

    $logDir = Join-Path $AppDirectory "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    foreach ($key in $EnvExtra.Keys) {
        & $Config.NssmPath set $Name AppEnvironmentExtra "$key=$($EnvExtra[$key])"
    }

    & $Config.NssmPath start $Name
    Start-Sleep -Seconds 2
    $svc = Get-Service -Name $Name
    Write-Host "  Status: $($svc.Status)" -ForegroundColor $(if ($svc.Status -eq "Running") { "Green" } else { "Red" })
}

# --- API ---
Install-NssmService `
    -Name "mehreagan-api" `
    -App $uvicorn `
    -AppDirectory $Config.BackendRoot `
    -AppParameters @(
        "app.main:app",
        "--host", $Config.ApiHost,
        "--port", "$($Config.ApiPort)",
        "--workers", "$($Config.ApiWorkers)"
    ) `
    -EnvExtra @{
        "PYTHONUTF8" = "1"
    }

# --- RabbitMQ consumer ---
Install-NssmService `
    -Name "mehreagan-consumer" `
    -App $python `
    -AppDirectory $Config.BackendRoot `
    -AppParameters @("-m", "app.infrastructure.messaging.consumer") `
    -EnvExtra @{
        "PYTHONUTF8" = "1"
    }

# --- Next.js ---
Install-NssmService `
    -Name "mehreagan-frontend" `
    -App $npmCmd `
    -AppDirectory $Config.FrontendRoot `
    -AppParameters @("run", "start") `
    -EnvExtra @{
        "PORT" = "$($Config.FrontendPort)"
        "NODE_ENV" = "production"
    }

# --- IIS web.config ---
$iisRoot = $Config.IisSiteRoot
$webConfigSrc = Join-Path $Config.BackendRoot "deploy\windows\web.config"
if (-not (Test-Path $iisRoot)) {
    New-Item -ItemType Directory -Path $iisRoot -Force | Out-Null
}
Copy-Item -Path $webConfigSrc -Destination (Join-Path $iisRoot "web.config") -Force
Write-Host ""
Write-Host "Copied web.config -> $iisRoot" -ForegroundColor Green
Write-Host ""
Write-Host "Next manual steps:" -ForegroundColor Cyan
Write-Host "  1. IIS: create site pointing to $iisRoot with HTTPS binding (win-acme)"
Write-Host "  2. Enable ARR proxy on the server"
Write-Host "  3. Allow serverVariables HTTP_X_FORWARDED_PROTO and HTTP_X_FORWARDED_HOST in ARR if rewrite fails"
Write-Host "  4. Windows Firewall: allow 443/80 only; block 8000/3000 from public"
Write-Host "  5. Run seed scripts once, then register backup: .\register-backup-task.ps1"
Write-Host ""
Write-Host "Verify:" -ForegroundColor Cyan
Write-Host "  curl https://erp.example.com/backend/health"
Write-Host "  Get-Service mehreagan-api, mehreagan-consumer, mehreagan-frontend"
