# Nous Companion — Windows install script
# Usage: iwr -useb https://git.io/nous-companion-install | iex
# Or:   iwr -useb https://raw.githubusercontent.com/realartsbro/Nous-Companion/main/scripts/install.ps1 | iex

$Repo = "realartsbro/Nous-Companion"
$Tag = "v0.1.2"
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

# Find the portable binary
$Exe = Get-ChildItem -Path $InstallDir -Recurse -Filter "nous-companion.exe" | Select-Object -First 1
if ($Exe) {
    Write-Host ""
    Write-Host "  ✅ Portable build ready!" -ForegroundColor Green
    Write-Host "  Binary: $($Exe.FullName)"
    Write-Host ""
    Write-Host "  Run directly: $($Exe.FullName)"
    Write-Host "  Or run the launcher for WSL setup:"
    $Launcher = Join-Path $Exe.Directory.FullName "launch-portable.bat"
    if (Test-Path $Launcher) {
        Write-Host "    $Launcher"
    }
    Write-Host ""
    Write-Host "  Or install properly via Start Menu:"
    $Installer = Get-ChildItem -Path $InstallDir -Recurse -Filter "*setup.exe" | Select-Object -First 1
    if ($Installer) {
        Write-Host "    $($Installer.FullName)"
    }
}
else {
    Write-Host "  WARNING: Could not find nous-companion.exe in $InstallDir" -ForegroundColor Yellow
}
