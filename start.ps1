# Launcher for the TikTok BR real-time translator.
# ASCII only on purpose: Windows PowerShell 5.1 mis-parses this file when it
# contains non-ASCII text, which made the old .bat exit instantly.

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $PSCommandPath }
$app = Join-Path $root 'app.py'

function Fail($msg) {
    Write-Host ''
    Write-Host 'START FAILED:' -ForegroundColor Red
    Write-Host $msg -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Take a screenshot of this window and send it to the assistant.' -ForegroundColor Cyan
    Read-Host 'Press Enter to close'
    exit 1
}

if (-not (Test-Path $app)) { Fail "app.py not found: $app" }

# Locate Python. libs/ ships cp312 binaries, so prefer EXACTLY 3.12:
# the 'py' launcher may otherwise pick another version (e.g. Anaconda 3.9).
$python = $null
$pyArgs = @()
$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $ok312 = $false
    try {
        & $pyLauncher.Source -3.12 -c "print(1)" *> $null
        $ok312 = ($LASTEXITCODE -eq 0)
    } catch { $ok312 = $false }
    if ($ok312) {
        $python = $pyLauncher.Source
        $pyArgs = @('-3.12', $app)
        Write-Host 'Python : py -3.12' -ForegroundColor DarkGray
    } else {
        $python = $pyLauncher.Source
        $pyArgs = @('-3', $app)
    }
} else {
    $cands = @(Get-Command python.exe -ErrorAction SilentlyContinue)
    foreach ($c in $cands) {
        if ($c.Source -notlike '*WindowsApps*') { $python = $c.Source; break }
    }
    if ($python) { $pyArgs = @($app) }
}
if (-not $python) {
    Fail @'
Python 3.12 (64-bit) not found.
This tool needs exactly Python 3.12 because libs/ contains cp312 binaries.
Download: https://www.python.org/downloads/release/python-3129/  (Windows installer 64-bit)
Tick "Add python.exe to PATH" during setup, then run this again.
'@
}

Write-Host 'Starting TikTok BR real-time translator ...' -ForegroundColor Green
Write-Host "Python : $python"
Write-Host "App    : $app"
Write-Host ''

# Remove the "downloaded from the internet" mark, if present.
Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.py', '.bat', '.ps1' } |
    ForEach-Object {
        try {
            if (Get-Item $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue) {
                Unblock-File -Path $_.FullName
                Write-Host "Unblocked: $($_.Name)" -ForegroundColor DarkGray
            }
        } catch { }
    }

# Run the app; keep the console open if it fails.
$env:PYTHONIOENCODING = 'utf-8'
$code = 0
try {
    & $python @pyArgs
    $code = $LASTEXITCODE
} catch {
    Fail $_.Exception.Message
}

if ($code -ne 0) {
    Fail "app.py exited with code $code"
}
