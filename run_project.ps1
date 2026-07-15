$projectDir = "C:\Users\MEDHA TRUST\Desktop\B2B-Project"
$backendLog = "$projectDir\backend.log"
$backendErrLog = "$projectDir\backend_err.log"
$frontendLog = "$projectDir\frontend.log"

# Clear any stale log files
Remove-Item $backendLog -ErrorAction SilentlyContinue
Remove-Item $backendErrLog -ErrorAction SilentlyContinue
Remove-Item $frontendLog -ErrorAction SilentlyContinue

Write-Host "=== Starting PipelineIQ ==="

# Start backend
$backendProc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", "$projectDir\launch_backend.ps1") `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErrLog `
    -NoNewWindow -PassThru

Write-Host "Backend started: PID $($backendProc.Id)"

# Start frontend
$frontendProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", "cd /d `"$projectDir\frontend`" && npm run dev") `
    -RedirectStandardOutput $frontendLog `
    -NoNewWindow -PassThru

Write-Host "Frontend started: PID $($frontendProc.Id)"

# Wait for backend
Write-Host "Waiting 15s for startup..."
Start-Sleep -Seconds 15

Write-Host ""
Write-Host "=== Backend log (last 15 lines) ==="
if (Test-Path $backendLog) { Get-Content $backendLog | Select-Object -Last 15 }
if (Test-Path $backendErrLog) {
    Write-Host "=== Backend stderr ==="
    Get-Content $backendErrLog | Select-Object -Last 10
}
Write-Host ""
Write-Host "=== Frontend log (last 10 lines) ==="
if (Test-Path $frontendLog) { Get-Content $frontendLog | Select-Object -Last 10 }

Write-Host ""
Write-Host "=== Health check ==="
try {
    $h = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "Backend: $($h.Content)"
} catch {
    Write-Host "Backend not responding yet"
}

Write-Host ""
Write-Host "Backend PID : $($backendProc.Id)  alive=$(-not $backendProc.HasExited)"
Write-Host "Frontend PID: $($frontendProc.Id)  alive=$(-not $frontendProc.HasExited)"
