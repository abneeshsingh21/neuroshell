param(
    [string]$AppName = "NeuroShell",
    [switch]$Preview,
    [switch]$IncludeCurrentUser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Parse-Version {
    param([string]$DisplayVersion)
    if ([string]::IsNullOrWhiteSpace($DisplayVersion)) {
        return [version]"0.0.0"
    }

    try {
        return [version]$DisplayVersion
    }
    catch {
        return [version]"0.0.0"
    }
}

$searchRoots = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
)

if ($IncludeCurrentUser) {
    $searchRoots += "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
}

$entries = @()
foreach ($root in $searchRoots) {
    $entries += Get-ItemProperty $root -ErrorAction SilentlyContinue |
        Where-Object {
            $_.PSObject.Properties.Name -contains "DisplayName" -and
            $_.PSObject.Properties.Name -contains "PSChildName" -and
            $_.DisplayName -eq $AppName -and
            $_.PSChildName -match '^\{[0-9A-Fa-f-]+\}$'
        } |
        ForEach-Object {
            [pscustomobject]@{
                ProductCode   = $_.PSChildName
                DisplayName   = $_.DisplayName
                DisplayVersion = $_.DisplayVersion
                Version       = Parse-Version -DisplayVersion $_.DisplayVersion
                Scope         = if ($root.StartsWith("HKCU:")) { "CurrentUser" } else { "LocalMachine" }
                InstallLocation = $_.InstallLocation
            }
        }
}

if (-not $entries -or $entries.Count -eq 0) {
    Write-Host "No $AppName MSI entries found."
    exit 0
}

$ordered = $entries | Sort-Object @{ Expression = "Version"; Descending = $true }, @{ Expression = "ProductCode"; Descending = $false }
$keep = $ordered[0]
$remove = @($ordered | Select-Object -Skip 1)

Write-Host "Newest entry kept:"
Write-Host "  ProductCode: $($keep.ProductCode)"
Write-Host "  Version:     $($keep.DisplayVersion)"
Write-Host "  Scope:       $($keep.Scope)"
if ($keep.InstallLocation) {
    Write-Host "  Location:    $($keep.InstallLocation)"
}

if ($remove.Count -eq 0) {
    Write-Host "No older $AppName MSI entries to remove."
    exit 0
}

Write-Host ""
Write-Host "Older entries detected:"
$remove | ForEach-Object {
    Write-Host "  $($_.ProductCode)  version=$($_.DisplayVersion)  scope=$($_.Scope)"
}

if ($Preview) {
    Write-Host ""
    Write-Host "Preview mode enabled. No uninstall actions executed."
    exit 0
}

if (-not (Test-IsAdmin)) {
    Write-Error "Administrator PowerShell is required for uninstall actions. Re-run in elevated PowerShell or use -Preview."
    exit 1
}

Write-Host ""
foreach ($entry in $remove) {
    Write-Host "Removing $($entry.ProductCode) (version $($entry.DisplayVersion)) ..."
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList @("/x", $entry.ProductCode, "/qn", "/norestart") -PassThru -Wait
    if ($proc.ExitCode -eq 0) {
        Write-Host "  Removed successfully."
    }
    else {
        Write-Host "  Removal returned ExitCode=$($proc.ExitCode)"
    }
}

Write-Host ""
Write-Host "Cleanup pass complete."
