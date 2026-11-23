@echo off
REM Optional: builds a standalone "Audio Pro Control.exe" (needs Python installed).
cd /d "%~dp0"
py -3 -m pip install --user --upgrade pyinstaller || goto :fail
py -3 -m PyInstaller --noconfirm --onefile --windowed --icon app.ico --add-data "app.ico;." --add-data "ui.html;." --name "Audio Pro Control" AudioProControl.pyw || goto :fail
echo.
echo Done: dist\Audio Pro Control.exe
pause
exit /b 0
:fail
echo Build failed.
pause
