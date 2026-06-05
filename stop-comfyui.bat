@echo off
echo 正在关闭 ComfyUI...
taskkill /F /IM python.exe /T 2>nul
if %errorlevel% equ 0 (
    echo ComfyUI 已关闭。
) else (
    echo 未找到运行中的 ComfyUI 进程。
)
pause
