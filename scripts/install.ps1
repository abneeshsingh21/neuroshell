# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# NeuroShell Universal 1-Line Installer for Windows
# Usage: irm https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.ps1 | iex

$ErrorActionPreference = "Stop"

$Version = "5.7.0"
$Repo = "abneeshsingh21/neuroshell"
$DownloadUrl = "https://github.com/$Repo/releases/latest/download/NeuroShell.exe"

$InstallDir = "$env:LOCALAPPDATA\Programs\NeuroShell"
$ExeTarget = "$InstallDir\NeuroShell.exe"
$CliTarget = "$InstallDir\NeuroShell-CLI.exe"

Write-Host ""
Write-Host "╭────────────────────────────────────────────────────────╮" -ForegroundColor Cyan
Write-Host "│  ⌬ NeuroShell v$Version — Native Enterprise Terminal    │" -ForegroundColor White
Write-Host "╰────────────────────────────────────────────────────────╯" -ForegroundColor Cyan
Write-Host ""

Write-Host "📦 Creating installation directory: $InstallDir..." -ForegroundColor DarkGray
if (!(Test-Path -Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

Write-Host "⬇️  Downloading NeuroShell.exe from GitHub Releases..." -ForegroundColor Cyan
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $DownloadUrl -OutFile $ExeTarget -UseBasicParsing

Copy-Item -Path $ExeTarget -Destination $CliTarget -Force

# Add to User PATH if not already present
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$InstallDir*") {
    Write-Host "🔧 Adding $InstallDir to User PATH environment variable..." -ForegroundColor DarkGray
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$InstallDir", "User")
    $env:Path = "$env:Path;$InstallDir"
}

# Create Desktop Shortcut
$WshShell = New-Object -ComObject WScript.Shell
$DesktopDir = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$DesktopDir\NeuroShell.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExeTarget
$Shortcut.WorkingDirectory = "$env:USERPROFILE"
$Shortcut.Description = "NeuroShell AI Intelligent Terminal"
$Shortcut.Save()

Write-Host ""
Write-Host "✨ NeuroShell v$Version successfully installed!" -ForegroundColor Green
Write-Host "  • Desktop Shortcut: Created on Desktop" -ForegroundColor White
Write-Host "  • Terminal Command: Run 'NeuroShell' from any prompt" -ForegroundColor White
Write-Host "  • Instant Launch: Starting NeuroShell..." -ForegroundColor Cyan
Write-Host ""

Start-Process -FilePath $ExeTarget
