Param(
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 3307,
    [string]$DbName = "jisparking",
    [string]$DbUser = "reader_user",
    [string]$DbPassword = "",
    [int]$ApiPort = 8093
)

$ErrorActionPreference = "Stop"

# Resolve repository root no matter where the script is executed from.
$repoRoot = Split-Path -Parent $PSScriptRoot

# Prefer project virtual environment if present.
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $workspaceVenv = Join-Path (Split-Path -Parent $repoRoot) ".venv\Scripts\python.exe"
    if (Test-Path $workspaceVenv) {
        $pythonExe = $workspaceVenv
    }
    else {
        $pythonExe = "python"
    }
}

$env:DB_HOST = $DbHost
$env:DB_PORT = "$DbPort"
$env:DB_NAME = $DbName
$env:DB_USER = $DbUser
$env:DB_PASSWORD = $DbPassword
$env:SQL_MAX_ROWS = "200"
$env:SQL_TIMEOUT_MS = "15000"
$env:SQL_AUDIT_FILE = "./logs/jis_chatsql_audit.jsonl"
$env:SQL_REQUIRE_ALLOWLIST = "false"

Push-Location $repoRoot
try {
    & $pythonExe -m pip install -r (Join-Path $repoRoot "requirements.txt")
    & $pythonExe -m uvicorn src.app:app --host 127.0.0.1 --port $ApiPort
}
finally {
    Pop-Location
}
