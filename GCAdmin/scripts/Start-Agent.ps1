$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Executa Instalar.bat primeiro.'
}
$config = Join-Path $env:LOCALAPPDATA 'GCAdmin\agent.json'
if (-not (Test-Path -LiteralPath $config)) {
    & $python -m gcadmin.agent --init
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar a configuracao.' }
    Start-Process notepad.exe -ArgumentList ('"' + $config + '"') -Wait
}
if (-not $env:GCADMIN_AGENT_TOKEN) {
    Write-Host 'Usa uma senha exclusiva de 24+ caracteres. Esta sera a senha no GCAdmin.'
    $secret = Read-Host 'Senha do agente' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $env:GCADMIN_AGENT_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}
try {
    & $python -m gcadmin.agent
    if ($LASTEXITCODE -ne 0) { throw 'O agente terminou com erro.' }
} finally {
    Remove-Item Env:GCADMIN_AGENT_TOKEN -ErrorAction SilentlyContinue
}
