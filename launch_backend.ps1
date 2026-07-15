Set-Location "C:\Users\MEDHA TRUST\Desktop\B2B-Project"

# Clear OS env overrides — .env file becomes the sole config source
[System.Environment]::SetEnvironmentVariable("OPENROUTER_MODEL", $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_BASE_URL", $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_MAX_TOKENS", $null, "Process")
[System.Environment]::SetEnvironmentVariable("OPENROUTER_TEMPERATURE", $null, "Process")

$cleared = [System.Environment]::GetEnvironmentVariable("OPENROUTER_MODEL", "Process")
Write-Host "OPENROUTER_MODEL after clear: [$cleared]"
Write-Host "Starting PipelineIQ backend on port 8000..."

& py -m uvicorn backend.main:app --reload --port 8000 --host 127.0.0.1
