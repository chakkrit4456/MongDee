@echo off
REM ตัวติดตั้ง MONGDEE AI Booth OS สำหรับ Windows
REM
REM วิธีใช้:
REM   install.bat          ติดตั้งรุ่น CPU (ใช้ได้ทุกเครื่อง แนะนำสำหรับส่วนใหญ่)
REM   install.bat --gpu    ติดตั้งรุ่นเร่งความเร็วด้วย NVIDIA GPU (ต้องมีการ์ดจอ NVIDIA)
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo  MONGDEE AI Booth OS - Installer (Windows)
echo ================================================

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    echo         Be sure to check "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/5] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/5] Virtual environment already exists, skipping.
)

call ".venv\Scripts\activate.bat"

echo [2/5] Upgrading pip...
python -m pip install --upgrade pip --quiet

set GPU_MODE=0
if "%1"=="--gpu" set GPU_MODE=1

if "%GPU_MODE%"=="1" (
    echo [3/5] Installing PyTorch ^(GPU/NVIDIA CUDA build - large download, ~2-3GB^)...
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
) else (
    echo [3/5] Installing PyTorch ^(CPU build - works on any PC, ~200MB^)...
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
)

echo [4/5] Installing remaining libraries (OpenCV, YOLO, PySide6, voice, web server, ...)...
pip install opencv-python ultralytics PySide6 pyttsx3 SpeechRecognition sounddevice numpy fastapi "uvicorn[standard]" jinja2 python-multipart openpyxl --quiet

echo [5/5] Creating shortcuts...
(
echo @echo off
echo cd /d "%%~dp0"
echo call ".venv\Scripts\activate.bat"
echo python launcher.py
) > run_launcher.bat

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\MONGDEE AI Booth OS.lnk');" ^
    "$s.TargetPath = '%~dp0run_launcher.bat';" ^
    "$s.WorkingDirectory = '%~dp0';" ^
    "$s.IconLocation = '%~dp0assets\icon.ico';" ^
    "$s.Save()"

echo.
echo Installation complete!
echo Launch from the Desktop shortcut "MONGDEE AI Booth OS", or run run_launcher.bat
pause
