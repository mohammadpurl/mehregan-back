# Run workflow/user seed scripts once after first `docker compose up -d`
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..\..")

Write-Host "Running seed scripts inside backend container..." -ForegroundColor Cyan

$scripts = @(
    "scripts/ensure_procurement_workflow_setup.py",
    "scripts/ensure_payment_workflow_setup.py",
    "scripts/ensure_petty_cash_workflow_setup.py",
    "scripts/ensure_payment_order_workflow_setup.py",
    "scripts/seed_financial_document_workflow.py",
    "scripts/seed_mission_request_workflow.py",
    "scripts/seed_sla_policies.py",
    "scripts/seed_ceo_user.py"
)

foreach ($script in $scripts) {
    Write-Host "  -> $script"
    docker compose exec -T backend python $script
    if ($LASTEXITCODE -ne 0) {
        throw "Seed failed: $script"
    }
}

Write-Host "Seed completed." -ForegroundColor Green
