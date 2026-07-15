Set-Location "C:\Users\MEDHA TRUST\Desktop\B2B-Project"

# Remove OS env overrides so .env file is the sole config source
[System.Environment]::SetEnvironmentVariable("OPENROUTER_MODEL",       $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY",     $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_BASE_URL",    $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_MAX_TOKENS",  $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_TEMPERATURE", $null, "Process")

$model = [System.Environment]::GetEnvironmentVariable("OPENROUTER_MODEL", "Process")
Write-Host "OPENROUTER_MODEL after clear: [$model]"
Write-Host "Starting backend on http://127.0.0.1:8000 ..."

py -m uvicorn backend.main:app --reload --port 8000 --host 127.0.0.1
