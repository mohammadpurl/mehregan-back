# Build images locally and export .tar files for offline transfer to server
# Usage: .\build-and-export.ps1 -PublicApiUrl "https://erp.example.com/backend"

param(
    [Parameter(Mandatory = $true)]
    [string]$PublicApiUrl,

    [string]$OutputDir = ".\dist"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

if (-not (Test-Path ".env")) {
    throw "Create Backend2/.env first (copy deploy\docker\.env.example)"
}

$env:NEXT_PUBLIC_API_URL = $PublicApiUrl

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Write-Host "Building images (this may take a while)..." -ForegroundColor Cyan
docker compose build --build-arg NEXT_PUBLIC_API_URL=$PublicApiUrl

$images = @(
    @{ Name = "mehragan-erp-backend"; Service = "backend" },
    @{ Name = "mehragan-erp-frontend"; Service = "frontend" }
)

foreach ($item in $images) {
    $id = docker compose images -q $item.Service
    if (-not $id) { throw "No image for service $($item.Service)" }
    docker tag $id "$($item.Name):latest"
    $tar = Join-Path $OutputDir "$($item.Name).tar"
    docker save "$($item.Name):latest" -o $tar
    Write-Host "Saved $tar" -ForegroundColor Green
}

Write-Host ""
Write-Host "Also transfer:" -ForegroundColor Cyan
Write-Host "  - docker-compose.yml"
Write-Host "  - .env (production secrets)"
Write-Host "  - deploy\windows\web.config -> IIS site folder"
Write-Host ""
Write-Host "On server:" -ForegroundColor Cyan
Write-Host "  docker load -i mehragan-erp-backend.tar"
Write-Host "  docker load -i mehragan-erp-frontend.tar"
Write-Host "  docker compose up -d"
