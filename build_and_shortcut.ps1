Write-Host "Building NeuroShell desktop release..."
python scripts\build_desktop_release.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete! Creating/Updating Desktop shortcut..."
    $WshShell = New-Object -comObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("$HOME\Desktop\NeuroShell.lnk")
    $Shortcut.TargetPath = "C:\Users\lenovo\Desktop\LLM model train\neuroshell\release\dist\NeuroShell.exe"
    $Shortcut.WorkingDirectory = "C:\Users\lenovo\Desktop\LLM model train\neuroshell\release\dist"
    $Shortcut.Save()
    Write-Host "Shortcut created successfully on Desktop!"
} else {
    Write-Host "Build failed with exit code $LASTEXITCODE. Shortcut creation aborted."
    exit $LASTEXITCODE
}
