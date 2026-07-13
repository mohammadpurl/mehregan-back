#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Security checklist for Mehreagan ERP Docker on Windows Server.

.USAGE
  Set-ExecutionPolicy -Scope Process Bypass
  cd E:\ERP\Backend2
  .\deploy\docker\secure\security-check.ps1
#>

$ErrorActionPreference = "Continue"
$fail = 0

function Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Bad($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red; $script:fail++ }

Write-Host "=== Mehreagan ERP security check ===" -ForegroundColor Cyan

# 1) Compose file presence
$compose = Join-Path $PSScriptRoot "docker-compose.yml"
if (Test-Path $compose) { Ok "secure compose found" } else { Bad "missing docker-compose.yml" }

# 2) .env must exist and not be world-readable secrets in git
$envPath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "../../..")) ".env"
if (Test-Path $envPath) {
    Ok ".env present at $envPath"
    $envText = Get-Content $envPath -Raw
    if ($envText -match "CHANGE_ME") { Warn ".env still contains CHANGE_ME placeholders" }
    if ($envText -match "123456") { Bad ".env or seed password still uses weak 123456 — rotate CEO password" }
} else {
    Bad ".env missing — copy deploy/docker/secure/.env.example"
}

# 3) Running containers inspection
Write-Host "`n--- Container inspection ---" -ForegroundColor Cyan
$ids = docker compose -f $compose --env-file $envPath ps -q 2>$null
if (-not $ids) {
    Warn "secure stack not running (or wrong compose path)"
} else {
    foreach ($id in ($ids -split "\s+")) {
        if (-not $id) { continue }
        $name = (docker inspect -f "{{.Name}}" $id).TrimStart("/")
        $user = docker inspect -f "{{.Config.User}}" $id
        $priv = docker inspect -f "{{.HostConfig.Privileged}}" $id
        $ro = docker inspect -f "{{.HostConfig.ReadonlyRootfs}}" $id
        $caps = docker inspect -f "{{json .HostConfig.CapDrop}}" $id
        $ports = docker inspect -f "{{json .NetworkSettings.Ports}}" $id

        Write-Host "`n  Container: $name" -ForegroundColor White
        if ($priv -eq "true") { Bad "$name is privileged=true" } else { Ok "$name privileged=false" }
        if ($user -eq "" -or $user -eq "0" -or $user -eq "root") {
            if ($name -match "postgres|rabbitmq") {
                Warn "$name User=$user (official image default; OK if not root at runtime)"
            } else {
                Bad "$name runs as User='$user' (expect non-root e.g. 10001)"
            }
        } else {
            Ok "$name User=$user"
        }
        if ($ro -eq "true") { Ok "$name read_only=true" } else { Warn "$name read_only=false" }
        if ($caps -match "ALL") { Ok "$name CapDrop includes ALL" } else { Warn "$name CapDrop=$caps" }

        # Public ports must only be 80/443
        if ($ports -match '"80/tcp"' -or $ports -match '"443/tcp"') {
            Ok "$name publishes 80/443 (edge)"
        }
        if ($ports -match '0\.0\.0\.0:8080' -or $ports -match '0\.0\.0\.0:8081' -or $ports -match '0\.0\.0\.0:8000' -or $ports -match '0\.0\.0\.0:3000' -or $ports -match '0\.0\.0\.0:5432') {
            Bad "$name publishes sensitive port on 0.0.0.0 — should be 127.0.0.1 or internal only"
        }
    }
}

# 4) Host listening ports
Write-Host "`n--- Host listeners (8080/8081/8000/3000/5432) ---" -ForegroundColor Cyan
$listen = netstat -ano | Select-String "LISTENING" | Select-String ":80 |:443 |:8080|:8081|:8000|:3000|:5432|:5672"
$listen | ForEach-Object { Write-Host "  $_" }

# 5) Firewall rules for 80/443
Write-Host "`n--- Firewall ---" -ForegroundColor Cyan
$fw80 = Get-NetFirewallRule -DisplayName "*80*" -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq "True" -and $_.Direction -eq "Inbound" }
$fw443 = Get-NetFirewallRule -DisplayName "*443*" -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq "True" -and $_.Direction -eq "Inbound" }
if ($fw80) { Ok "Inbound rule related to 80 found" } else { Warn "No obvious firewall rule for HTTP 80" }
if ($fw443) { Ok "Inbound rule related to 443 found" } else { Warn "No obvious firewall rule for HTTPS 443 (OK if HTTP-only for now)" }

# 6) Docker socket exposure
Write-Host "`n--- Docker Desktop / daemon ---" -ForegroundColor Cyan
try {
    $info = docker info 2>&1 | Out-String
    if ($info -match "Security Options") { Ok "docker info reachable" }
    if ($info -match "userns") { Ok "userns mentioned in docker info" } else { Warn "userns-remap not detected (Docker Desktop limitation — OK)" }
} catch {
    Bad "docker info failed"
}

Write-Host ""
if ($fail -gt 0) {
    Write-Host "Completed with $fail FAIL item(s)." -ForegroundColor Red
    exit 1
}
Write-Host "Security check finished with no FAIL items." -ForegroundColor Green
exit 0
