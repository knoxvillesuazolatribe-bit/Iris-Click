<#
Builds IrisClick Desktop: the app folder and (if Inno Setup 6 is installed) IrisClick-Desktop-Setup.exe.

    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-CloudUrl https://iris-click.vercel.app] [-SkipInstaller]

What goes in packaging\out\IrisClick-Desktop (committed files only, never server\.env or local data):
  runtime\   Python 3.12 from this PC's own python.org install (includes tkinter, which the
             control bar and on-screen keyboard need) + the app's packages from server\.venv
             (the exact versions IrisClick is tested with)
  server\    the server, tracking worker and launcher (git HEAD, without tests)
  server\.env  ONLY the public website address (IRISCLICK_CLOUD_URL). No database password:
             the desktop app syncs through the hosted server (database option 2).
  irisclick.ico
The shortcut runs:  runtime\pythonw.exe server\launch_irisclick.pyw
The website itself is hosted (Vercel); it is not inside the installer.
Commit your changes first: the build uses the committed code (HEAD).
#>
param(
    [string]$CloudUrl = "https://iris-click.vercel.app",
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $PSScriptRoot "out"
$App = Join-Path $Out "IrisClick-Desktop"
$Work = Join-Path $Out "work"
$Venv = Join-Path $Repo "server\.venv"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Copy-Tree($from, $to, [string[]]$excludeDirs = @()) {
    $args = @($from, $to, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1")
    if ($excludeDirs.Count) { $args += "/XD"; $args += $excludeDirs }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copy failed: $from -> $to (robocopy $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

Step "Checking"
if ($CloudUrl -notmatch '^https://[^/\s]+$') { throw "CloudUrl must look like https://example.app (no path)." }
$pyVenv = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $pyVenv)) { throw "server\.venv is missing. Set up the server first (README)." }
$Base = (& $pyVenv -c "import sys; print(sys.base_prefix)").Trim()
$PyVersion = (& $pyVenv -c "import sys; print('%d.%d.%d' % sys.version_info[:3])").Trim()
if (-not $PyVersion.StartsWith("3.12.")) { throw "IrisClick needs Python 3.12 (found $PyVersion)." }
& (Join-Path $Base "python.exe") -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) { throw "The Python install at $Base has no tkinter. Reinstall Python 3.12 with Tcl/Tk." }
$Version = (& $pyVenv -c "import sys; sys.path.insert(0, r'$Repo\server'); from app.version import VERSION; print(VERSION)").Trim()
$dirty = git -C $Repo status --porcelain -- server packaging
if ($dirty) { Write-Warning "Uncommitted changes are NOT in the build (it uses HEAD):`n$($dirty -join "`n")" }
$Commit = (git -C $Repo rev-parse --short HEAD).Trim()
Write-Host "IrisClick Desktop $Version ($Commit); Python $PyVersion from $Base; website $CloudUrl"

Step "Cleaning packaging\out"
foreach ($dir in $App, $Work) { if (Test-Path $dir) { Remove-Item -Recurse -Force $dir } }
New-Item -ItemType Directory -Force $App, $Work | Out-Null

Step "Python runtime (without its own extra packages, tests or docs)"
$Runtime = Join-Path $App "runtime"
New-Item -ItemType Directory -Force $Runtime | Out-Null
foreach ($f in "python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt") {
    $src = Join-Path $Base $f
    if (Test-Path $src) { Copy-Item $src $Runtime }
}
Copy-Tree (Join-Path $Base "DLLs") (Join-Path $Runtime "DLLs")
Copy-Tree (Join-Path $Base "tcl") (Join-Path $Runtime "tcl")
Copy-Tree (Join-Path $Base "Lib") (Join-Path $Runtime "Lib") @("site-packages", "test", "idlelib", "ensurepip", "__pycache__", "tkinter\test", "lib2to3\tests")

Step "App packages from server\.venv"
Copy-Tree (Join-Path $Venv "Lib\site-packages") (Join-Path $Runtime "Lib\site-packages") @("__pycache__", "pip", "_pytest", "pytest", "pluggy", "iniconfig")
$pth = Get-ChildItem (Join-Path $Runtime "Lib\site-packages") -Filter *.pth -ErrorAction SilentlyContinue |
    Where-Object { (Get-Content $_.FullName -Raw) -match "[A-Za-z]:\\" }
if ($pth) { Write-Warning "These .pth files point at fixed paths and may not work elsewhere: $($pth.Name -join ', ')" }

Step "Server code (git HEAD)"
$zip = Join-Path $Work "server.zip"
git -C $Repo archive --format=zip -o $zip HEAD server
Expand-Archive $zip -DestinationPath $App
Remove-Item -Recurse -Force (Join-Path $App "server\tests")
Set-Content -Path (Join-Path $App "server\VERSION.txt") -Value "IrisClick Desktop $Version ($Commit)" -Encoding ascii
# Public settings only. DB_HOST stays empty: desktop mode, local database + sync (option 2).
Set-Content -Path (Join-Path $App "server\.env") -Encoding ascii -Value @(
    "# IrisClick Desktop settings (no secrets). Written by packaging\build.ps1.",
    "IRISCLICK_CLOUD_URL=$CloudUrl",
    "AUTO_START_WORKER=true"
)

Step "Icon"
& $pyVenv (Join-Path $PSScriptRoot "make_icon.py") (Join-Path $App "irisclick.ico") | Out-Null

Step "Checking the app folder"
$py = Join-Path $Runtime "python.exe"
& $py -I -c "import sys; sys.path.insert(0, r'$App\server'); import tkinter, cv2, mediapipe, fastapi, uvicorn, pyttsx3, pystray, edge_tts, app.api.main, app.launcher, app.desktop_sync.sync; print('imports ok')"
if ($LASTEXITCODE -ne 0) { throw "The app folder cannot import IrisClick's packages." }
$size = "{0:N0} MB" -f ((Get-ChildItem $App -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "App folder: $App ($size)"
Remove-Item -Recurse -Force $Work

if ($SkipInstaller) { Write-Host "Installer skipped (-SkipInstaller)."; exit 0 }
Step "Installer (Inno Setup 6)"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Warning "Inno Setup 6 is not installed, so only the app folder was built. Install it from https://jrsoftware.org/isdl.php and run this script again."
    exit 0
}
& $iscc "/DAppVersion=$Version" "/DSourceDir=$App" "/O$Out" (Join-Path $PSScriptRoot "irisclick-desktop.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Installer: $(Join-Path $Out 'IrisClick-Desktop-Setup.exe')" -ForegroundColor Green
