param(
    [ValidateSet('Set', 'Status', 'Run')][string]$Action = 'Set',
    [string]$JobId
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$secretPath = Join-Path $projectRoot 'results_1060\personal_curriculum\secrets\openrouter.dpapi'

if ($Action -eq 'Status') {
    if (Test-Path -LiteralPath $secretPath -PathType Leaf) {
        Write-Host 'Encrypted OpenRouter key is saved for this Windows account.'
    } else {
        Write-Host 'OpenRouter key has not been saved yet.'
    }
    return
}

if ($Action -eq 'Set') {
    $secretValue = Read-Host 'Paste your OpenRouter API key (hidden)' -AsSecureString
    try {
        if ($secretValue.Length -eq 0) { throw 'No key entered; nothing saved.' }
        $encryptedValue = ConvertFrom-SecureString -SecureString $secretValue
        $secretFolder = Split-Path -Parent $secretPath
        New-Item -ItemType Directory -Path $secretFolder -Force | Out-Null
        [System.IO.File]::WriteAllText($secretPath, $encryptedValue, [System.Text.Encoding]::UTF8)
        Write-Host 'Saved with Windows encryption for your account. No API request was made.'
    } finally {
        $secretValue.Dispose()
        $encryptedValue = $null
    }
    return
}

if ($JobId -notmatch '^[0-9a-f]{64}$') { throw 'Run requires one saved headset job identity.' }
if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) { throw 'Save the key first with -Action Set.' }
$secretValue = ConvertTo-SecureString -String ([System.IO.File]::ReadAllText($secretPath, [System.Text.Encoding]::UTF8))
$secretPointer = [IntPtr]::Zero
$previousValue = $env:OPENROUTER_API_KEY
try {
    $secretPointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretValue)
    $env:OPENROUTER_API_KEY = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
    $queueRoot = Join-Path $projectRoot 'results_1060\accuracy_program_20261004\frontier_bridge\data'
    & (Join-Path $projectRoot 'venv1060\Scripts\python.exe') (Join-Path $PSScriptRoot 'openrouter_audio_queue.py') --root $queueRoot run --execute --id $JobId
    if ($LASTEXITCODE -ne 0) { throw 'Comparison stopped. Review its saved status before trying again.' }
} finally {
    $env:OPENROUTER_API_KEY = $previousValue
    $previousValue = $null
    if ($secretPointer -ne [IntPtr]::Zero) { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer) }
    $secretValue.Dispose()
}
