@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"

if /I "%~1"=="start" goto do_start
if /I "%~1"=="stop" goto do_stop
if /I "%~1"=="status" goto do_status
if /I "%~1"=="open" goto do_open
if /I "%~1"=="start-lite" goto do_start_lite

:menu
cls
echo =====================================================
echo      HoneyHive Studio ????? (GUI BAT)
echo =====================================================
echo ???: %ROOT%
echo.
echo [1] ????????
echo [2] ????
echo [3] ??????
echo [4] ?????? (GUI/API)
echo [5] ?????? (??? Telegram Bot)
echo [Q] ??
echo.
choice /C 12345Q /N /M "?????: "
if errorlevel 6 goto end
if errorlevel 5 goto do_start_lite_pause
if errorlevel 4 goto do_open_pause
if errorlevel 3 goto do_status_pause
if errorlevel 2 goto do_stop_pause
if errorlevel 1 goto do_start_pause
goto menu

:do_start_pause
call :do_start
pause
goto menu

:do_stop_pause
call :do_stop
pause
goto menu

:do_status_pause
call :do_status
pause
goto menu

:do_open_pause
call :do_open
pause
goto menu

:do_start_lite_pause
call :do_start_lite
pause
goto menu

:do_start
echo [RUN] ??????...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start-all-services.ps1" -Root "%ROOT%"
exit /b %ERRORLEVEL%

:do_start_lite
echo [RUN] ????????? Telegram Bot?...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start-all-services.ps1" -Root "%ROOT%" -StartTelegramBot:$false
exit /b %ERRORLEVEL%

:do_stop
echo [RUN] ??????...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\stop-all-services.ps1" -Root "%ROOT%"
exit /b %ERRORLEVEL%

:do_status
echo [INFO] ????????...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\check-services-status.ps1" -Root "%ROOT%"
exit /b %ERRORLEVEL%

:do_open
echo [OPEN] ??????...
start "" "http://127.0.0.1:8501"
start "" "http://127.0.0.1:8503"
start "" "http://127.0.0.1:8188"
exit /b 0

:end
echo ????
endlocal
