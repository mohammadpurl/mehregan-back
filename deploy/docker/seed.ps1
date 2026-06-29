# Run once after first `docker compose up -d` on an empty database.
#
# Usage:
#   cd E:\ERP\Backend2\deploy\docker
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\seed.ps1
#
# Optional: grant super-admin to CEO after seed:
#   .\seed.ps1 -GrantSuperAdminToCeo
# Or by numeric id (see seed_ceo_user output for user_id):
#   .\seed.ps1 -GrantSuperAdminUserId 3

param(
    [int]$GrantSuperAdminUserId = 0,
    [switch]$GrantSuperAdminToCeo
)

$ErrorActionPreference = "Stop"

# Docker/Python log to stderr; PS 5.1 treats that as a terminating error with Stop.
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$backendRoot = Join-Path $PSScriptRoot "..\.."
Set-Location $backendRoot

function Invoke-BackendScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
        [string[]]$ScriptArgs
    )
    Write-Host "  -> $Label" -ForegroundColor Cyan
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $seedOutput = docker compose exec -T backend python @ScriptArgs 2>&1
        $seedOutput | Write-Host
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "--- script output ---" -ForegroundColor Red
        $seedOutput | Write-Host
        throw "Seed failed: $Label (exit $LASTEXITCODE)"
    }
}

Write-Host "=== Mehreagan ERP database seed ===" -ForegroundColor Green
Write-Host "Working directory: $backendRoot"

if (-not (docker compose ps -q backend 2>$null)) {
    throw "backend container is not running. Run: docker compose up -d"
}

Invoke-BackendScript "apply_schema_patches.py" "scripts/apply_schema_patches.py"

try {
    Invoke-BackendScript "reset_rbac.py" "scripts/reset_rbac.py" "--yes"
} catch {
    Write-Host "reset_rbac failed - trying non-destructive seed_rbac_if_empty.py ..." -ForegroundColor Yellow
    Invoke-BackendScript "seed_rbac_if_empty.py" "scripts/seed_rbac_if_empty.py"
}

$workflowScripts = @(
    "scripts/ensure_procurement_workflow_setup.py",
    "scripts/ensure_payment_workflow_setup.py",
    "scripts/ensure_petty_cash_workflow_setup.py",
    "scripts/ensure_payment_order_workflow_setup.py",
    "scripts/seed_financial_document_workflow.py",
    "scripts/seed_mission_request_workflow.py"
)
foreach ($script in $workflowScripts) {
    Invoke-BackendScript $script $script
}

Invoke-BackendScript "seed_sla_policies.py" "scripts/seed_sla_policies.py"
Invoke-BackendScript "seed_ceo_user.py" "scripts/seed_ceo_user.py"

if ($GrantSuperAdminToCeo) {
    Invoke-BackendScript "grant_role_to_user.py" `
        "scripts/grant_role_to_user.py" `
        "--username" "mjyounesi" `
        "--role" "super-admin"
} elseif ($GrantSuperAdminUserId -gt 0) {
    Invoke-BackendScript "grant_role_to_user.py" `
        "scripts/grant_role_to_user.py" `
        "--user-id" "$GrantSuperAdminUserId" `
        "--role" "super-admin"
}

Write-Host ""
Write-Host "Seed completed." -ForegroundColor Green
Write-Host "IMPORTANT: log out and log in again so menu permissions refresh." -ForegroundColor Yellow
Write-Host "CEO login: username=mjyounesi  password=123456  (change after first login)" -ForegroundColor Yellow
Write-Host 'For full menus during setup, run: .\seed.ps1 -GrantSuperAdminToCeo' -ForegroundColor Yellow
