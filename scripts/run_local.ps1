Param(
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 3307,
    [string]$DbName = "jisparking",
    [string]$DbUser = "reader_user",
    [string]$DbPassword = "",
    [int]$ApiPort = 8093
)

$ErrorActionPreference = "Stop"

$env:DB_HOST = $DbHost
$env:DB_PORT = "$DbPort"
$env:DB_NAME = $DbName
$env:DB_USER = $DbUser
$env:DB_PASSWORD = $DbPassword
$env:SQL_MAX_ROWS = "200"
$env:SQL_TIMEOUT_MS = "15000"
$env:SQL_AUDIT_FILE = "./logs/jis_chatsql_audit.jsonl"
$env:SQL_REQUIRE_ALLOWLIST = "false"

python -m pip install -r requirements.txt
python -m uvicorn src.app:app --host 127.0.0.1 --port $ApiPort
