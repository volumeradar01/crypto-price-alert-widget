<#
    build.ps1 — produce a standalone build and (if Inno Setup is present) a Windows installer.

    Usage:   powershell -ExecutionPolicy Bypass -File build.ps1
    Output:  dist\CryptoPriceAlert\           self-contained app folder (portable)
             installer_output\CryptoPriceAlertSetup-<ver>.exe   one-click installer
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# --- 1. Python / venv -------------------------------------------------
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host 'Creating virtual environment (.venv) ...'
    try { & py -3 -m venv .venv } catch { & python -m venv .venv }
}
if (-not (Test-Path $py)) { throw 'Could not create .venv - install Python 3.10+ first.' }

Write-Host 'Installing build dependencies ...'
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements.txt pyinstaller | Out-Null

# --- 2. icon -------------------------------------------------------
Write-Host 'Generating app icon ...'
& $py packaging\make_ico.py

# --- 3. freeze with PyInstaller --------------------------------
Write-Host 'Freezing app with PyInstaller (this can take a few minutes) ...'
if (Test-Path build)  { Remove-Item build  -Recurse -Force }
if (Test-Path dist)   { Remove-Item dist   -Recurse -Force }
& $py -m PyInstaller --noconfirm --clean packaging\CryptoPriceAlert.spec

$exe = Join-Path $root 'dist\CryptoPriceAlert\CryptoPriceAlert.exe'
if (-not (Test-Path $exe)) { throw "PyInstaller build failed - $exe not found." }
Write-Host "OK  standalone app: dist\CryptoPriceAlert\" -ForegroundColor Green

# --- 4. installer (Inno Setup) --------------------------------
$candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles        'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA        'Programs\Inno Setup 6\ISCC.exe')
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source }

if (-not $iscc) {
    Write-Warning 'Inno Setup 6 not found - installer not built.'
    Write-Host    'Install it, then re-run this script:'
    Write-Host    '    winget install --id JRSoftware.InnoSetup -e'
    Write-Host    '    (or download from https://jrsoftware.org/isdl.php )'
    Write-Host    ''
    Write-Host    "Meanwhile, the portable build is ready - zip this folder:  dist\CryptoPriceAlert\"
    exit 0
}

Write-Host "Building installer with $iscc ..."
& $iscc packaging\installer.iss
$setup = Get-ChildItem (Join-Path $root 'installer_output') -Filter *.exe -ErrorAction SilentlyContinue |
         Sort-Object LastWriteTime | Select-Object -Last 1
if ($setup) {
    Write-Host ("OK  installer: installer_output\{0}  ({1:N1} MB)" -f $setup.Name, ($setup.Length / 1MB)) -ForegroundColor Green
} else {
    throw 'Inno Setup ran but no installer .exe was produced - check the output above.'
}
