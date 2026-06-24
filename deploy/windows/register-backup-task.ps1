#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Register daily PostgreSQL + uploads backup in Windows Task Scheduler.

.USAGE
  .\register-backup-task.ps1
#>

$ErrorActionPreference = "Stop"

$TaskName = "Mehreagan-ERP-Daily-Backup"
$ScriptPath = Join-Path $PSScriptRoot "backup-postgres.ps1"

if (-not (Test-Path $ScriptPath)) {
    throw "backup-postgres.ps1 not found next to this script."
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Scheduled task registered: $TaskName (daily 02:00)" -ForegroundColor Green
Write-Host "Test now: powershell -File `"$ScriptPath`""
