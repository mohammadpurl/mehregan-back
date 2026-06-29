# Export built images for offline transfer to server
# Usage: .\export-images.ps1

$ErrorActionPreference = "Stop"
$outDir = Join-Path $PSScriptRoot "..\..\dist"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$names = @(
    "mehragan-erp-backend:latest",
    "mehragan-erp-frontend:latest"
)

foreach ($name in $names) {
    $id = docker images -q $name
    if (-not $id) {
        Write-Host "Missing image: $name — run docker compose build first" -ForegroundColor Red
        exit 1
    }
    $file = Join-Path $outDir ($name -replace ":", "-" -replace "/", "_") + ".tar"
    Write-Host "Saving $name -> $file"
    docker save $name -o $file
}

Write-Host ""
Write-Host "Copy dist\*.tar to server, then:" -ForegroundColor Green
Write-Host "  docker load -i mehragan-erp-backend-latest.tar"
Write-Host "  docker load -i mehragan-erp-frontend-latest.tar"
Write-Host "  docker compose up -d"
