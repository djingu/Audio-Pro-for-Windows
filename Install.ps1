# Installs Audio Pro Control for the current user:
#  - makes sure Python 3 is available (installs it with winget if not)
#  - copies the app to %LOCALAPPDATA%\AudioProControl
#  - adds Start menu and Desktop shortcuts, then starts the app
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA 'AudioProControl'

function Find-PythonW {
    $cands = @()
    foreach ($py in @('py', "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe", "$env:WINDIR\py.exe")) {
        try {
            $exe = & $py -3 -c "import sys,os,tkinter;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { $cands += $exe.Trim() }
        } catch {}
    }
    $cands += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object FullName
    $cands += Get-ChildItem "$env:ProgramFiles\Python3*\pythonw.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object FullName
    foreach ($c in $cands) { if ($c -and (Test-Path $c)) { return $c } }
    return $null
}

Write-Host "Audio Pro Control - installer" -ForegroundColor Cyan
# close a running copy so its files can be replaced
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:47811/api/ping | Out-Null; Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*AudioProControl.pyw*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } } catch {}
$pyw = Find-PythonW
if (-not $pyw) {
    Write-Host "Python 3 was not found. Installing it with winget (one-time, ~30 MB)..."
    winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
    $pyw = Find-PythonW
    if (-not $pyw) {
        Write-Host "Could not find Python after installing. Install Python 3 from python.org, then run Install.bat again." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
}
Write-Host "Using $pyw"

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item (Join-Path $here 'AudioProControl.pyw') $dest -Force
Copy-Item (Join-Path $here 'app.ico') $dest -Force
Copy-Item (Join-Path $here 'ui.html') $dest -Force

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Audio Pro Control.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Audio Pro Control.lnk')
)
foreach ($lnkPath in $targets) {
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + (Join-Path $dest 'AudioProControl.pyw') + '"'
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = (Join-Path $dest 'app.ico')
    $lnk.Description = 'Control Audio Pro Wi-Fi speakers'
    $lnk.Save()
}

Write-Host "Installed. Shortcuts added to the Start menu and Desktop." -ForegroundColor Green
Start-Process -FilePath $pyw -ArgumentList ('"' + (Join-Path $dest 'AudioProControl.pyw') + '"') -WorkingDirectory $dest
Start-Sleep -Seconds 2
