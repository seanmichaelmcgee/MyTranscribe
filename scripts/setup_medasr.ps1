# Run from PowerShell; leaves venv1060 and the Windows app untouched.
param([string]$Python = "", [string]$CaBundle = "")
$ErrorActionPreference = "Stop"
$taskRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
if (!$Python) { $Python = Join-Path $taskRoot "venv1060\Scripts\python.exe" }
if (!$CaBundle) {
    $candidate = Join-Path $taskRoot "venv1060\ssl\ca-bundle.pem"
    if (Test-Path -LiteralPath $candidate) { $CaBundle = $candidate }
}
if ($CaBundle) {
    $env:PIP_CERT = (Resolve-Path -LiteralPath $CaBundle).Path
    $env:SSL_CERT_FILE = $env:PIP_CERT
    $env:REQUESTS_CA_BUNDLE = $env:PIP_CERT
}
$trialPython = Join-Path $taskRoot "venvmedasr\Scripts\python.exe"
if (!(Test-Path -LiteralPath $trialPython)) {
    & $Python -m venv venvmedasr
    if ($LASTEXITCODE) { throw "Could not create isolated environment" }
}
# Extended paths prevent WinError 206 in PyTorch's deeply nested license files.
# No registry or global long-path setting changes.
$installPython = "\\?\" + $trialPython
& $installPython -m pip install --only-binary=:all: torch==2.13.0 --index-url https://download.pytorch.org/whl/cu126
if ($LASTEXITCODE) { throw "PyTorch installation failed" }
& $installPython -m pip install --only-binary=:all: -r requirements-medasr.txt -c requirements-medasr.lock.txt
if ($LASTEXITCODE) { throw "MedASR dependencies failed" }
& $installPython -m pip check
if ($LASTEXITCODE) { throw "Dependency check failed" }
& $trialPython -c 'import torch; from transformers import LasrForCTC, LasrProcessor; print("torch", torch.__version__, "CUDA", torch.cuda.is_available()); print("GPU", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"); print("architectures", torch.cuda.get_arch_list())'
if ($LASTEXITCODE) { throw "Runtime import check failed" }
Write-Host "Runtime ready. Model access is separate; see docs/MEDASR_TRIAL.md."
