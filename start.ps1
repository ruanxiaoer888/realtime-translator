# Launcher for the TikTok BR real-time translator.
# ASCII only on purpose: Windows PowerShell 5.1 mis-parses this file when it
# contains non-ASCII text, which made the old .bat exit instantly.

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
# Start-Process -NoNewWindow is used to get a process object: we need to tell
# "it started" from "it died instantly" -- minimize the console in the first case,
# leave the traceback on screen in the second.
$env:PYTHONIOENCODING = 'utf-8'
# -ArgumentList joins the array into one string, so paths with spaces need quotes
# (e.g. project under "D:\My Projects\..." would otherwise split into two args).
$argList = @($pyArgs | ForEach-Object { if ("$_" -match '\s') { '"' + $_ + '"' } else { "$_" } })
$proc = $null
try {
    $proc = Start-Process -FilePath $python -ArgumentList $argList -PassThru -NoNewWindow
} catch {
    Fail $_.Exception.Message
}

Start-Sleep -Milliseconds 2500
if ($proc.HasExited) {
    Fail "app.py exited immediately with code $($proc.ExitCode)"
}

Hide-Console
$proc.WaitForExit()

if ($proc.ExitCode -ne 0) {
    Fail "app.py exited with code $($proc.ExitCode)"
}
