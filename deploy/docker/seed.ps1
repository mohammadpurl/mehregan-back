# Run once after first `docker compose up -d` on an empty database.
#
# Usage:
#   cd E:\ERP\Backend2\deploy\docker
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\seed.ps1
#
# Optional: grant super-admin to user id after seed:
#   .\seed.ps1 -GrantSuperAdminUserId 1

param(
    [int]$GrantSuperAdminUserId = 0
)

$ErrorActionPreference = "Stop"

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
    docker compose exec -T backend python @ScriptArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Seed failed: $Label"
    }
}

Write-Host "=== Mehreagan ERP database seed ===" -ForegroundColor Green
Write-Host "Working directory: $backendRoot"

if (-not (docker compose ps -q backend 2>$null)) {
    throw "backend container is not running. Run: docker compose up -d"
}

Invoke-BackendScript "apply_schema_patches.py" "scripts/apply_schema_patches.py"
Invoke-BackendScript "reset_rbac.py" "scripts/reset_rbac.py" "--yes"

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

if ($GrantSuperAdminUserId -gt 0) {
    Write-Host "Granting super-admin to user id $GrantSuperAdminUserId ..." -ForegroundColor Yellow
    docker compose exec -T backend python -c @"
from app.core.database import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole

db = SessionLocal()
user = db.get(User, $GrantSuperAdminUserId)
role = db.query(Role).filter(Role.name == 'super-admin').first()
if not user or not role:
    raise SystemExit('user or super-admin role not found')
link = db.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first()
if link:
    link.is_active = True
else:
    db.add(UserRole(user_id=user.id, role_id=role.id, is_active=True))
db.commit()
print(f'granted super-admin to user_id={user.id} username={user.username}')
db.close()
"@
    if ($LASTEXITCODE -ne 0) { throw "Grant super-admin failed" }
}

Write-Host ""
Write-Host "Seed completed." -ForegroundColor Green
Write-Host "IMPORTANT: log out and log in again so menu permissions refresh." -ForegroundColor Yellow
Write-Host "CEO login: username=mjyounesi  password=123456  (change after first login)" -ForegroundColor Yellow
Write-Host "For full menus during setup, run: .\seed.ps1 -GrantSuperAdminUserId <USER_ID>" -ForegroundColor Yellow
