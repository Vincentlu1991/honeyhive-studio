@echo off
setlocal
cd /d "%~dp0"
call scripts\service-control-gui.bat
endlocal
