@echo off
REM Builds the web version into  %USERPROFILE%\Downloads\RetailInvoiceWeb\RetailInvoiceWeb.exe
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller flask waitress reportlab
python -m PyInstaller --noconfirm --clean --console --name RetailInvoiceWeb ^
  --add-data "%~dp0templates;templates" ^
  --distpath "%USERPROFILE%\Downloads" --workpath build --specpath build ^
  app.py
echo.
echo Done. Copy the folder "%USERPROFILE%\Downloads\RetailInvoiceWeb" to the client PC.
pause
