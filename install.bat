@echo off
REM ═══════════════════════════════════════════════════════════
REM NeuroShell v4 — Windows Installer Script
REM One-click setup for Windows users
REM ═══════════════════════════════════════════════════════════

echo.
echo  ============================================
echo   🧠 NeuroShell v4 — AI-Powered Terminal
echo   Windows Installer
echo  ============================================
echo.

REM ── Check Python ──
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ❌ Python is not installed or not in PATH.
    echo  📥 Download from: https://python.org/downloads
    pause
    exit /b 1
)

echo  ✅ Python found.

REM ── Create virtual environment ──
if not exist ".venv" (
    echo  📦 Creating virtual environment...
    python -m venv .venv
)

REM ── Activate venv ──
call .venv\Scripts\activate.bat

REM ── Upgrade pip ──
echo  ⬆️  Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

REM ── Install core dependencies ──
echo  📦 Installing core dependencies...
pip install -r requirements.txt

REM ── Install optional extras ──
echo  📦 Installing optional extras (LLM, NLP, Desktop GUI)...
pip install ollama>=0.3 groq>=0.4 scikit-learn>=1.3 nltk>=3.8 customtkinter>=5.2 pyperclip>=1.8 2>nul

REM ── Check Ollama ──
echo.
echo  🤖 Checking for Ollama...
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo  ⚠️  Ollama not found.
    echo  📥 Download from: https://ollama.com/download
    echo  💡 After installing, run: ollama pull qwen3:4b
) else (
    echo  ✅ Ollama found.
    echo  📥 Pulling default model (qwen3:4b)...
    ollama pull qwen3:4b 2>nul
)

REM ── Create launch shortcuts ──
echo.
echo  🔗 Creating launch scripts...

REM CLI launcher
(
echo @echo off
echo call "%~dp0.venv\Scripts\activate.bat"
echo python "%~dp0main.py" %%*
) > neuroshell.bat

REM Desktop launcher
(
echo @echo off
echo call "%~dp0.venv\Scripts\activate.bat"
echo python "%~dp0desktop_app.py" %%*
) > neuroshell-desktop.bat

echo.
echo  ============================================
echo   ✅ Installation Complete!
echo  ============================================
echo.
echo   Launch options:
echo     CLI:     neuroshell.bat
echo     Desktop: neuroshell-desktop.bat
echo.
echo   Or activate venv manually:
echo     .venv\Scripts\activate
echo     python main.py
echo.
pause
