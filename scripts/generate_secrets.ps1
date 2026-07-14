# Generate cryptographically strong secrets for .env (prints to stdout; does not write files).
# Usage:  powershell -File .\scripts\generate_secrets.ps1
# Then paste into Backend2/.env and Frontend .env — never commit real values.

function New-ErpSecret([int]$Bytes = 48) {
    $buf = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    [Convert]::ToBase64String($buf).TrimEnd('=')
}

Write-Host "# Paste into production .env then discard this terminal output"
Write-Host "SECRET_KEY=$(New-ErpSecret 48)"
Write-Host "JWT_SERVER_SECRET=$(New-ErpSecret 48)"
Write-Host "POSTGRES_PASSWORD=$(New-ErpSecret 24)"
Write-Host "RABBITMQ_PASSWORD=$(New-ErpSecret 24)"
Write-Host "OTP_API_KEY=$(New-ErpSecret 32)"
Write-Host "OTP_SECRET=$(New-ErpSecret 24)"
Write-Host ""
Write-Host "# Also set:"
Write-Host "ENVIRONMENT=production"
Write-Host "RATE_LIMIT_ENABLED=true"
Write-Host "# ENABLE_API_DOCS=false   # leave unset/false on public internet"
Write-Host "# Create users with: python scripts/create_admin_user.py --username admin --password `"...`""
