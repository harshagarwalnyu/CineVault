# Movies Recommender - Native Windows Turbo Script (v2.1)
# Usage: ./turbo.ps1

# Fix emoji encoding in PowerShell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

write-host "==========================================================" -ForegroundColor Cyan
write-host "  🚀 Project NEBULA: Native Windows Turbo Mode" -ForegroundColor Cyan
write-host "  Bypassing Docker/WSL2 for Maximum Performance" -ForegroundColor Cyan
write-host "==========================================================" -ForegroundColor Cyan

# 1. Environment Synchronization
write-host "`n[1/3] Syncing Environments..." -ForegroundColor Yellow

if (Test-Path .env) {
    write-host "🔑 Loading environment from .env..." -ForegroundColor Gray
    Get-Content .env | ForEach-Object {
        $trimmed = $_.Trim()
        if ($trimmed -and !$trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
            $name, $value = $trimmed.split("=", 2)
            $cleanName = $name.Trim()
            $cleanValue = $value.Trim().Trim('"').Trim("'")
            if ($cleanValue -match "\s+#") { $cleanValue = $cleanValue.split("#")[0].Trim() }
            [System.Environment]::SetEnvironmentVariable($cleanName, $cleanValue, "Process")
        }
    }
}

# Ensure critical NextAuth variable is present
if (![System.Environment]::GetEnvironmentVariable("AUTH_SECRET", "Process")) {
    $defaultSecret = "supersecretcomplexstring12345"
    [System.Environment]::SetEnvironmentVariable("AUTH_SECRET", $defaultSecret, "Process")
    [System.Environment]::SetEnvironmentVariable("NEXTAUTH_SECRET", $defaultSecret, "Process")
}

# Check and KILL locked files (uvicorn/node)
$runningProcesses = Get-Process -Name "uvicorn", "node", "python" -ErrorAction SilentlyContinue
if ($runningProcesses) {
    write-host "⚠️  Closing existing Backend/Frontend processes to unlock files..." -ForegroundColor Yellow
    $runningProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# Backend Sync (uv)
write-host "🐍 Syncing Backend (uv)..." -ForegroundColor Gray
uv sync

# Frontend Sync (detect manager)
write-host "🍞 Analyzing Frontend Environment..." -ForegroundColor Gray
$pkgManager = "npm"
if (Get-Command bun -ErrorAction SilentlyContinue) { $pkgManager = "bun" }
elseif (Get-Command pnpm -ErrorAction SilentlyContinue) { $pkgManager = "pnpm" }

write-host "Using $pkgManager to sync dependencies..." -ForegroundColor Gray
Set-Location frontend
if ($pkgManager -eq "npm") { npm install }
else { Invoke-Expression "$pkgManager install" }
Set-Location ..

# 2. Ports and URLs
$API_URL = "http://localhost:8000"
$FRONTEND_URL = "http://localhost:3002"

# 3. Launching Services
write-host "`n[2/3] Launching Services in Parallel..." -ForegroundColor Yellow

$CurrentDir = $PWD.Path

# Launch Backend in a new window
$BackendCommand = 'cd "{0}"; $env:PYTHONPATH="."; uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload' -f $CurrentDir
$BackendArgs = @("-NoExit", "-Command", $BackendCommand)
write-host "🚀 Starting Backend..." -ForegroundColor Gray
Start-Process powershell -ArgumentList $BackendArgs -WindowStyle Normal

# Launch Frontend in a new window
$DevCmd = if ($pkgManager -eq "bun") { "bun dev --port 3002 --turbo" } else { "$pkgManager run dev -- --port 3002" }
$FrontendCommand = 'cd "{0}/frontend"; $env:NEXT_PUBLIC_API_URL="{1}"; {2}' -f $CurrentDir, $API_URL, $DevCmd
$FrontendArgs = @("-NoExit", "-Command", $FrontendCommand)
write-host "🚀 Starting Frontend..." -ForegroundColor Gray
Start-Process powershell -ArgumentList $FrontendArgs -WindowStyle Normal

# 4. Status
write-host "`n[3/3] Success!" -ForegroundColor Green
write-host "----------------------------------------------------------"
write-host "  🎥 Frontend: $FRONTEND_URL" -ForegroundColor Cyan
write-host "  🧠 API Docs: $API_URL/docs" -ForegroundColor Cyan
write-host "----------------------------------------------------------"
write-host "  Press Ctrl+C in those windows to stop.`n"
