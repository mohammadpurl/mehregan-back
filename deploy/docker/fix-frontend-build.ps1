# Run once on server from E:\ERP\Backend2 before docker compose build frontend
# Fixes legacy verification-form on disk AND verifies compose uses deploy Dockerfile.

$ErrorActionPreference = "Stop"

$backendRoot = $PSScriptRoot | Split-Path | Split-Path
$frontendRoot = Join-Path (Split-Path $backendRoot) "Frontend-Next3\erp"
$verificationForm = Join-Path $frontendRoot "app\(auth)\_components\verification-form.tsx"
$composeFile = Join-Path $backendRoot "docker-compose.yml"

Write-Host "Backend:  $backendRoot" -ForegroundColor Cyan
Write-Host "Frontend: $frontendRoot" -ForegroundColor Cyan

if (-not (Test-Path $frontendRoot)) {
    throw "Frontend not found: $frontendRoot"
}

@'
'use client';
export { SignInForm as VerificationForm } from './sign-in-form';
'@ | Set-Content -Path $verificationForm -Encoding UTF8

Write-Host "Patched: $verificationForm" -ForegroundColor Green

$deployDockerfile = Join-Path $backendRoot "deploy\docker\frontend.Dockerfile"
if (-not (Test-Path $deployDockerfile)) {
    throw "Missing $deployDockerfile — git pull Backend2 repo"
}

$compose = Get-Content $composeFile -Raw
if ($compose -notmatch "deploy/docker/frontend\.Dockerfile") {
    Write-Host "WARNING: docker-compose.yml does not use deploy/docker/frontend.Dockerfile" -ForegroundColor Yellow
    Write-Host "Update frontend.build.dockerfile to: deploy/docker/frontend.Dockerfile" -ForegroundColor Yellow
} else {
    Write-Host "docker-compose.yml OK" -ForegroundColor Green
}

Write-Host ""
Write-Host "Now run:" -ForegroundColor Cyan
Write-Host "  cd $backendRoot"
Write-Host "  docker compose build frontend --no-cache"
Write-Host "  docker compose up -d"
