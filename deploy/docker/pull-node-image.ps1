# Pull Node base image via mirror and tag as node:20-alpine for Docker builds.
# Use when docker.io returns 403 on the server.
#
# Usage (from Backend2):
#   .\deploy\docker\pull-node-image.ps1
#   docker compose build frontend

$ErrorActionPreference = "Stop"

$mirrors = @(
    "docker.1ms.run/library/node:20-alpine",
    "docker.m.daocloud.io/library/node:20-alpine",
    "dockerproxy.com/library/node:20-alpine"
)

$target = "node:20-alpine"
$pulled = $false

foreach ($mirror in $mirrors) {
    Write-Host "Trying mirror: $mirror" -ForegroundColor Cyan
    docker pull $mirror
    if ($LASTEXITCODE -eq 0) {
        docker tag $mirror $target
        Write-Host "Tagged $target <- $mirror" -ForegroundColor Green
        $pulled = $true
        break
    }
    Write-Host "Mirror failed, trying next..." -ForegroundColor Yellow
}

if (-not $pulled) {
    throw @"
Could not pull node:20-alpine from any mirror.
Options:
  1) Build frontend on a PC with Docker Hub access, then: docker save ... | docker load on server
  2) Copy updated Frontend-Next3/Dockerfile (uses ARG NODE_IMAGE) to the server
  3) Try: docker login  then pull node:20-alpine
"@
}

Write-Host ""
Write-Host "OK. Now run:" -ForegroundColor Green
Write-Host "  cd E:\ERP\Backend2"
Write-Host "  docker compose build frontend"
