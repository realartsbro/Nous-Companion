# Nous Companion — Windows install script
# Usage: iwr -useb https://git.io/nous-companion-install | iex
# Or:   iwr -useb https://raw.githubusercontent.com/realartsbro/Nous-Companion/main/scripts/install.ps1 | iex

$Repo = "realartsbro/Nous-Companion"
$Tag = "v0.1.1"
$InstallDir = "$env:LOCALAPPDATA\Nous-Companion"

Write-Host "⬡ Nous Companion" -ForegroundColor Cyan
Write-Host "  Installing to: $InstallDir"

# Create install directory
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

# Download URL using explicit tag
$DownloadUrl = "https://github.com/$Repo/releases/download/$Tag/Nous-Companion-windows.zip"
Write-Host "  Downloading..."
Write-Host "  URL: $DownloadUrl"

# Download the zip
$ZipPath = "$env:TEMP\nous-companion-windows.zip"
try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath -UseBasicParsing
}
catch {
    Write-Host "ERROR: Download failed: $_" -ForegroundColor Red
    exit 1
}

# Extract
Write-Host "  Extracting..."
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $InstallDir)
}
catch {
    Write-Host "ERROR: Extraction failed: $_" -ForegroundColor Red
    exit 1
}
Remove-Item $ZipPath -Force

# Find the installer
$Installer = Get-ChildItem -Path $InstallDir -Recurse -Filter "*setup.exe" | Select-Object -First 1
if ($Installer) {
    Write-Host "  Found installer: $($Installer.Name)"
    Write-Host "  Running installer (silent mode)..."
    Start-Process -Wait -FilePath $Installer.FullName -ArgumentList "/S"
    Write-Host "  ✅ Installation complete!" -ForegroundColor Green
    Write-Host "  Nous Companion is now installed. Launch from Start Menu."
}
else {
    # Try to find the raw exe
    $Exe = Get-ChildItem -Path $InstallDir -Recurse -Filter "nous-companion.exe" | Select-Object -First 1
    if ($Exe) {
        Write-Host "  Found binary: $($Exe.FullName)"
        Write-Host "  ⚠ This is the raw binary — it may not work without the proper installer."
        Write-Host "  Run: $($Exe.FullName)"
    }
    else {
        Write-Host "  WARNING: Could not find installer or binary in $InstallDir" -ForegroundColor Yellow
        Write-Host "  Files extracted:"
        Get-ChildItem -Path $InstallDir -Recurse -Depth 2 | Select-Object Name
    }
}
