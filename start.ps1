# Launcher for the TikTok BR real-time translator.
# ASCII ONLY on purpose: Windows PowerShell 5.1 mis-parses this file when it
# contains non-ASCII text (it decodes UTF-8 bytes as GBK), which made the old
# .bat exit instantly. 2026-10: adding Chinese comments here broke it AGAIN
# (the parser ate an assignment and $logDir came out empty) -- keep it ASCII.
# Chinese diagnostics live in app.py / check_deploy.py, not here.

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $PSCommandPath }
$app = Join-Path $root 'app.py'

# Console window handle: used to minimize this black box once the GUI is up.
# We keep the window (instead of closing it) because app.py errors need to show here.
Add-Type -Namespace Tk -Name Win -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@ -ErrorAction SilentlyContinue

function Hide-Console {
    try {
        $h = [Tk.Win]::GetConsoleWindow()
        if ($h -ne [IntPtr]::Zero) { [Tk.Win]::ShowWindow($h, 6) | Out-Null }   # 6 = SW_MINIMIZE
    } catch { }
}

function Show-Console {
    try {
        $h = [Tk.Win]::GetConsoleWindow()
        if ($h -ne [IntPtr]::Zero) { [Tk.Win]::ShowWindow($h, 9) | Out-Null }   # 9 = SW_RESTORE
    } catch { }
}

function Fail($msg) {
    Show-Console
    Write-Host ''
    Write-Host 'START FAILED:' -ForegroundColor Red
    Write-Host $msg -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Take a screenshot of this window and send it to the assistant.' -ForegroundColor Cyan
    Read-Host 'Press Enter to close'
    exit 1
}

function Find-Py312 {
    # Look for a real Python 3.12 python.exe, in order of likelihood.
    # Why this exists: if py.exe is present but `py -3.12` fails, the old code
    # fell back to `py -3`, which can pick 3.13/3.14 -- app.py then exits
    # immediately with "wrong Python version".
    $cands = @()
    $local = $env:LOCALAPPDATA
    if ($local) {
        $cands += (Join-Path $local 'Programs\Python\Python312\python.exe')
        $cands += (Join-Path $local 'Python\Python312\python.exe')
    }
    $cands += 'C:\Python312\python.exe'
    $cands += 'C:\Program Files\Python312\python.exe'
    foreach ($k in @(
        'HKLM:\SOFTWARE\Python\PythonCore\3.12\InstallPath',
        'HKCU:\SOFTWARE\Python\PythonCore\3.12\InstallPath',
        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath')) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).'(default)'
            if ($v) { $cands += (Join-Path $v 'python.exe') }
        } catch { }
    }
    foreach ($c in $cands) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    return $null
}

if (-not (Test-Path $app)) { Fail "app.py not found: $app" }

# Locate Python. libs/ ships cp312 binaries, so prefer EXACTLY 3.12:
# the 'py' launcher may otherwise pick another version (e.g. Anaconda 3.9),
# and a bare `python` on PATH may be 3.13/3.14.
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
    }
}
if (-not $python) {
    $p312 = Find-Py312
    if ($p312) {
        $python = $p312
        $pyArgs = @($app)
        Write-Host "Python : $p312 (3.12 found outside the py launcher)" -ForegroundColor DarkGray
    }
}
if (-not $python) {
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
# Start-Process -NoNewWindow is used to get a process object: we need to tell
# "it started" from "it died instantly" -- minimize the console in the first case,
# leave the traceback on screen in the second.
$env:PYTHONIOENCODING = 'utf-8'
# -ArgumentList joins the array into one string, so paths with spaces need quotes
# (e.g. project under "D:\My Projects\..." would otherwise split into two args).
$argList = @($pyArgs | ForEach-Object { if ("$_" -match '\s') { '"' + $_ + '"' } else { "$_" } })

# Keep a copy of app.py output as well: when the process is killed outright
# (antivirus / EDR on company machines) the console can show nothing at all,
# and these two files are then the only clue.
$logDir = Join-Path $root 'tmp'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logOut = Join-Path $logDir 'startup_log.txt'
$logErr = Join-Path $logDir 'startup_err.txt'
Remove-Item $logOut, $logErr -Force -ErrorAction SilentlyContinue

$proc = $null
try {
    $proc = Start-Process -FilePath $python -ArgumentList $argList -PassThru -NoNewWindow `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr
} catch {
    Fail $_.Exception.Message
}

# Two-stage probe (2.5s, then 2s more): a single 2.5s look can misread the
# hand-off between py.exe and the real python.exe as "it died".
$died = $false
Start-Sleep -Milliseconds 2500
if ($proc.HasExited) { Start-Sleep -Milliseconds 2000; $proc.Refresh() }
if ($proc.HasExited) {
    # Before declaring failure, check for a live app window: py.exe may have
    # exited while the python.exe child kept running.
    $alive = @(Get-Process -Name python -ErrorAction SilentlyContinue |
               Where-Object { $_.MainWindowTitle -like '*Translator*' })
    if ($alive.Count -gt 0) {
        Write-Host 'App window detected - treating as started.' -ForegroundColor DarkGray
    } else {
        $died = $true
    }
}

if ($died) {
    # Really failed. Re-run app.py in the foreground so the actual error stays
    # on screen, instead of the useless "exited with code" (which was even
    # empty in the real failure we hit).
    $code = $proc.ExitCode
    if ($null -eq $code) { $code = 'unknown' }
    Show-Console
    Write-Host ''
    Write-Host "app.py failed to start (exit code: $code)." -ForegroundColor Yellow
    Write-Host 'Re-running it in the foreground so the real error stays on screen:' -ForegroundColor Yellow
    Write-Host ('-' * 60) -ForegroundColor DarkGray
    if ((Test-Path $logErr) -and (Get-Item $logErr).Length -gt 0) {
        Write-Host '[tmp\startup_err.txt]' -ForegroundColor DarkGray
        Get-Content $logErr | Select-Object -Last 40 | Write-Host
        Write-Host ('-' * 60) -ForegroundColor DarkGray
    }
    & $python @pyArgs
    $code2 = $LASTEXITCODE
    Write-Host ('-' * 60) -ForegroundColor DarkGray
    Fail "app.py exited again in the foreground (exit code: $code2). Full log: tmp\startup_log.txt"
}

Hide-Console
$proc.WaitForExit()

if ($proc.ExitCode -ne 0) {
    Fail "app.py exited with code $($proc.ExitCode)"
}
