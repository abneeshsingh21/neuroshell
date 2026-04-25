@echo off
title NeuroShell Desktop
color 0A

REM ═══════════════════════════════════════════════════════
REM  NeuroShell Desktop — One-Click Launcher
REM  Double-click this file to launch NeuroShell Desktop
REM ═══════════════════════════════════════════════════════

echo.
echo   [38;5;51m=====================================[0m
echo   [38;5;51m  🧠 NeuroShell Desktop Launcher[0m
echo   [38;5;51m=====================================[0m
echo.

REM Navigate to the neuroshell directory
cd /d "%~dp0"

REM Set the LLM model (change this to your preferred model)
set NEUROSHELL_MODEL=qwen3:4b

REM Groq Cloud API key (fallback when Ollama is offline)
if "%GROQ_API_KEY%"=="" (
    REM Optional: uncomment and set your key if you want Groq fallback.
    REM set GROQ_API_KEY=your_groq_api_key_here
)

REM Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [31m❌ Python not found! Please install Python 3.10+[0m
    echo   [33m   Download: https://python.org/downloads[0m
    pause
    exit /b 1
)

REM Check if customtkinter is installed
python -c "import customtkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo   [33m📦 Installing required packages...[0m
    pip install customtkinter psutil rich ollama toml colorama pyperclip scikit-learn nltk >nul 2>&1
    echo   [32m✅ Packages installed![0m
)

REM Launch the desktop app
echo   [32m🚀 Launching NeuroShell Desktop...[0m
echo.

pythonw desktop_app.py 2>nul
if %errorlevel% neq 0 (
    python desktop_app.py
)
