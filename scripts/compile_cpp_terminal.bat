@echo off
setlocal enabledelayedexpansion

echo ================================================================
echo   Compiling NeuroShell Native Terminal with Embedded Icon
echo ================================================================

call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

if not exist "dist" mkdir "dist"

echo.
echo [1/2] Compiling Windows Resource Script (Embedding icon.ico)...
rc.exe /fo "dist\resource.res" "cpp_engine\launcher\resource.rc"
if %errorlevel% neq 0 (
    echo Error compiling resource script.
    exit /b %errorlevel%
)

echo.
echo [2/2] Compiling Native C++20 Win32 Terminal Executable...
cl.exe /O2 /std:c++20 /EHsc /utf-8 /DUNICODE /D_UNICODE ^
    "cpp_engine\launcher\main.cpp" "dist\resource.res" ^
    /Fe:"dist\NeuroShell.exe" ^
    /link user32.lib shell32.lib advapi32.lib

if %errorlevel% neq 0 (
    echo Error compiling C++ executable.
    exit /b %errorlevel%
)

echo.
echo ================================================================
echo   SUCCESS! Compiled Native Terminal: dist\NeuroShell.exe
echo ================================================================
