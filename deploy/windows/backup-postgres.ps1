<#
.SYNOPSIS
  Daily PostgreSQL backup for Mehreagan ERP (Windows).

.CONFIG
  Edit $Config below. Password can come from PGPASSWORD env or .env file.

.USAGE
  .\backup-postgres.ps1
  Scheduled via register-backup-task.ps1
#>

$ErrorActionPreference = "Stop"

$Config = @{
    PgDumpPath   = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
    BackupRoot   = "C:\apps\mehreagan\backups"
    BackendEnv   = "C:\apps\mehreagan\Backend2\.env"
    UploadsDir   = "C:\apps\mehreagan\Backend2\data\uploads"
    RetentionDays = 14
    # Override if not using DATABASE_URL in .env:
    DbHost       = "127.0.0.1"
    DbPort       = "5432"
    DbName       = "task_management"
    DbUser       = "erp_user"
}

function Read-DotEnvValue {
    param([string]$FilePath, [string]$Key)
    if (-not (Test-Path $FilePath)) { return $null }
    foreach ($line in Get-Content $FilePath -Encoding UTF8) {
        if ($line -match "^\s*$Key\s*=\s*(.+)\s*$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

function Parse-DatabaseUrl {
    param([string]$Url)
    if ($Url -match "^postgresql(?:\+psycopg)?://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(.+)$") {
        return @{
            User = $Matches[1]
            Password = [uri]::UnescapeDataString($Matches[2])
            Host = $Matches[3]
            Port = if ($Matches[4]) { $Matches[4] } else { "5432" }
            Database = $Matches[5].Split("?")[0]
        }
    }
    return $null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$dbDir = Join-Path $Config.BackupRoot "postgres"
$uploadDir = Join-Path $Config.BackupRoot "uploads"
New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
New-Item -ItemType Directory -Path $uploadDir -Force | Out-Null

$dbUser = $Config.DbUser
$dbName = $Config.DbName
$dbHost = $Config.DbHost
$dbPort = $Config.DbPort
$dbPassword = $env:PGPASSWORD

$databaseUrl = Read-DotEnvValue -FilePath $Config.BackendEnv -Key "DATABASE_URL"
if ($databaseUrl) {
    $parsed = Parse-DatabaseUrl -Url $databaseUrl
    if ($parsed) {
        $dbUser = $parsed.User
        $dbPassword = $parsed.Password
        $dbHost = $parsed.Host
        $dbPort = $parsed.Port
        $dbName = $parsed.Database
    }
}

if (-not $dbPassword) {
    $dbPassword = Read-DotEnvValue -FilePath $Config.BackendEnv -Key "POSTGRES_PASSWORD"
}

if (-not (Test-Path $Config.PgDumpPath)) {
    throw "pg_dump not found at $($Config.PgDumpPath). Adjust PgDumpPath for your PostgreSQL version."
}

$dumpSql = Join-Path $dbDir "task_management_$timestamp.sql"
$dumpZip = Join-Path $dbDir "task_management_$timestamp.zip"
$env:PGPASSWORD = $dbPassword

Write-Host "Backing up database $dbName on ${dbHost}:${dbPort} ..."

& $Config.PgDumpPath `
    -h $dbHost `
    -p $dbPort `
    -U $dbUser `
    -d $dbName `
    --no-owner `
    --no-acl `
    -F p `
    -f $dumpSql

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dumpSql)) {
    throw "pg_dump failed (exit $LASTEXITCODE)"
}

Compress-Archive -Path $dumpSql -DestinationPath $dumpZip -Force
Remove-Item $dumpSql -Force
$dumpFile = $dumpZip

Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
Write-Host "Database backup: $dumpFile"

if (Test-Path $Config.UploadsDir) {
    $uploadArchive = Join-Path $uploadDir "uploads_$timestamp.zip"
    Write-Host "Archiving uploads ..."
    Compress-Archive -Path (Join-Path $Config.UploadsDir "*") -DestinationPath $uploadArchive -Force
    Write-Host "Uploads backup: $uploadArchive"
}

$cutoff = (Get-Date).AddDays(-$Config.RetentionDays)
Get-ChildItem $dbDir -File | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
Get-ChildItem $uploadDir -File | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force

Write-Host "Done. Retention: $($Config.RetentionDays) days."
