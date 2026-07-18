
param(
    [string]$ProjectPath = "C:\Users\halle\only-cards"
)

$ErrorActionPreference = "Stop"

$HostName = "aws-1-ap-northeast-2.pooler.supabase.com"
$Port = "5432"
$Database = "postgres"
$Username = "postgres.xcxleflqihruqatwwvpq"

Set-Location $ProjectPath

$Python = Join-Path $ProjectPath "venv\Scripts\python.exe"
$SecurePassword = Read-Host "Enter your Supabase database password" -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)

try {
    $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
    $EncodedPassword = [uri]::EscapeDataString($PlainPassword)
    $env:DATABASE_URL = "postgresql://${Username}:${EncodedPassword}@${HostName}:${Port}/${Database}?sslmode=require"

    & $Python ".\scripts\backup_database.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Database backup failed."
    }
}
finally {
    if ($Bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
    Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
    $PlainPassword = $null
}
