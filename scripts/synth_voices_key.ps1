# Save the OpenAI API key for scripts/synth_voices.py, encrypted for this Windows account (DPAPI).
# The key is typed into a hidden prompt; it is never shown, logged or written in plain text.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\synth_voices_key.ps1          # save
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\synth_voices_key.ps1 -Status  # check
param([switch]$Status)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$secretPath = Join-Path $projectRoot 'results_1060\synthetic_voices\secrets\openai.dpapi'

if ($Status) {
    if (Test-Path -LiteralPath $secretPath -PathType Leaf) { Write-Host 'OpenAI key is saved for this Windows account.' }
    else { Write-Host 'OpenAI key has not been saved yet.' }
    return
}

$secretValue = Read-Host 'Paste your OpenAI API key (hidden), then press Enter' -AsSecureString
try {
    if ($secretValue.Length -eq 0) { throw 'No key entered; nothing saved.' }
    $encryptedValue = ConvertFrom-SecureString -SecureString $secretValue
    New-Item -ItemType Directory -Path (Split-Path -Parent $secretPath) -Force | Out-Null
    [System.IO.File]::WriteAllText($secretPath, $encryptedValue, [System.Text.Encoding]::UTF8)
    Write-Host 'Saved with Windows encryption for your account. No API request was made. You can close this tab.'
} finally {
    $secretValue.Dispose()
    $encryptedValue = $null
}
