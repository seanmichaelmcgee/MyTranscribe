@echo off
rem run_1060_checks.bat — unattended hardware checks for the Medical / GTX 1060 edition.
rem
rem No microphone needed: it generates fictional dictations with Windows' built-in
rem voices, simulates headset / conference-mic (Tenor-style) / noisy-room audio, and
rem runs them through the real model on your GPU.
rem
rem Run from the MyTranscribe folder after installing requirements-1060.txt:
rem     scripts\run_1060_checks.bat            (about 45-60 minutes)
rem     scripts\run_1060_checks.bat quick      (about 10 minutes)
rem
rem Everything goes to results_1060\. Send back results_1060\SUMMARY.txt (no PHI:
rem all audio is synthetic and fictional).

setlocal
cd /d "%~dp0\.."
set PY=venv1060\Scripts\python.exe
if not exist %PY% (
    echo venv1060 not found. Install first: see README_1060.md
    exit /b 1
)
set OUT=results_1060
if not exist %OUT% mkdir %OUT%
set SUM=%OUT%\SUMMARY.txt
echo MyTranscribe 1060 checks %DATE% %TIME% > %SUM%

echo [1/6] GPU and driver...
nvidia-smi > %OUT%\01_nvidia_smi.txt 2>&1
%PY% -c "import sys; sys.path.insert(0,'src'); import fw_engine; fw_engine.register_cuda_dll_dirs(); import ctranslate2 as c; print('ctranslate2', c.__version__, 'cuda devices', c.get_cuda_device_count()); print('compute types', sorted(c.get_supported_compute_types('cuda')) if c.get_cuda_device_count() else 'none')" > %OUT%\02_ctranslate2.txt 2>&1
type %OUT%\02_ctranslate2.txt >> %SUM%
findstr /L /C:"Driver Version" %OUT%\01_nvidia_smi.txt >> %SUM%

echo [2/6] Unit tests...
%PY% -m pytest -q tests > %OUT%\03_pytest.txt 2>&1
echo --- unit tests >> %SUM%
powershell -NoProfile -Command "Get-Content %OUT%\03_pytest.txt -Tail 1" >> %SUM%

echo [3/6] Generating synthetic dictations (Windows voices)...
if not exist %OUT%\testdict\manifest.json (
    %PY% scripts\make_test_dictation.py --out %OUT%\testdict --backend sapi > %OUT%\04_make_dictation.txt 2>&1
)
type %OUT%\04_make_dictation.txt >> %SUM%

echo [4/6] Speed and memory benchmark...
echo --- benchmark (clean / conference) >> %SUM%
%PY% scripts\bench_engine.py --audio %OUT%\testdict\fm_diabetes_htn__clean.wav --reference %OUT%\testdict\fm_diabetes_htn.txt --json %OUT%\05_bench_clean.json > %OUT%\05_bench_clean.txt 2>&1
%PY% scripts\bench_engine.py --audio %OUT%\testdict\fm_diabetes_htn__conference.wav --reference %OUT%\testdict\fm_diabetes_htn.txt --json %OUT%\05_bench_conf.json > %OUT%\05_bench_conf.txt 2>&1
findstr /L /C:"Config:" /C:"RTF" /C:"Peak" /C:"WER" %OUT%\05_bench_clean.txt %OUT%\05_bench_conf.txt >> %SUM%

echo [5/6] Accuracy across settings and mic profiles...
if /I "%1"=="quick" (
    set VARIANTS=static,topics+fix
) else (
    set VARIANTS=none,static,topics,topics+fix
)
%PY% scripts\eval_dictation.py --manifest %OUT%\testdict\manifest.json --variants %VARIANTS% --show-missed --json %OUT%\06_eval.json > %OUT%\06_eval.txt 2>&1
echo --- accuracy (WER %% / term recall %%) >> %SUM%
powershell -NoProfile -Command "$t = Get-Content %OUT%\06_eval.txt; $i = ($t | Select-String 'WER %%' | Select-Object -First 1).LineNumber; if ($i) { $t[($i-1)..($i+6)] }" >> %SUM%

echo [6/6] Stress tests with the real model...
if /I "%1"=="quick" (
    %PY% scripts\stress_pipeline.py --audio %OUT%\testdict\fm_cardiac__conference.wav --scenario long --minutes 3 --scenario faults --json %OUT%\07_stress.json > %OUT%\07_stress.txt 2>&1
) else (
    %PY% scripts\stress_pipeline.py --audio %OUT%\testdict\fm_cardiac__conference.wav --scenario long --minutes 15 --scenario cycles --cycles 100 --scenario silence --scenario faults --scenario gui --gui-cycles 10 --json %OUT%\07_stress.json > %OUT%\07_stress.txt 2>&1
)
echo --- stress >> %SUM%
findstr /L /C:"[PASS]" /C:"[FAIL]" /C:"ALL CHECKS" /C:"FAILED" /C:"rtf_mean" %OUT%\07_stress.txt >> %SUM%

echo.
echo Done. Summary:
type %SUM%
endlocal
