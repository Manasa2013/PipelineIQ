@echo off
cd /d "C:\Users\MEDHA TRUST\Desktop\B2B-Project"

REM Clear OS env overrides so .env is authoritative
set OPENROUTER_MODEL=
set OPENROUTER_API_KEY=
set OPENROUTER_BASE_URL=
set OPENROUTER_MAX_TOKENS=
set OPENROUTER_TEMPERATURE=

echo Starting PipelineIQ backend...
echo OPENROUTER_MODEL after clear: [%OPENROUTER_MODEL%]

py -m uvicorn backend.main:app --reload --port 8000 --host 127.0.0.1
