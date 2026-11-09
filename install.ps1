<#
.SYNOPSIS
    Install or update Text Tools for Flow Launcher without the plugin manager.

.DESCRIPTION
    Downloads the latest GitHub release zip (or uses -ZipPath), backs up any
    existing Text Tools plugin folder, extracts the new version into the Flow
    Launcher plugins folder and restarts Flow Launcher if it was running.

.EXAMPLE
    irm https://raw.githubusercontent.com/ghaemaghaey/Flow.Launcher.Plugin.TextTools/main/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -Version 2.0.0

.EXAMPLE
    .\install.ps1 -ZipPath .\TextTools-v2.0.0.zip -NoRestart
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:APPDATA 'FlowLauncher\Plugins'),
    [string]$Version,
    [string]$ZipPath,
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'
$Repo = 'ghaemaghaey/Flow.Launcher.Plugin.TextTools'
$PluginId = '39a68fde-a547-4bfc-8145-9cfa444c3ab5'
$Headers = @{
    'User-Agent' = 'TextTools-Installer'
    'Accept'     = 'application/vnd.github+json'
}

function Write-Step($Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-PluginFolders($Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    Get-ChildItem -LiteralPath $Root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $manifest = Join-Path $_.FullName 'plugin.json'
        if (Test-Path -LiteralPath $manifest) {
            try {
                $json = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($json.ID -eq $PluginId) { $_ }
            } catch {
                # Ignore folders with a broken manifest.
            }
        }
    }
}

function Find-PluginRoot($Path) {
    if (Test-Path -LiteralPath (Join-Path $Path 'plugin.json')) { return $Path }
    $inner = Get-ChildItem -LiteralPath $Path -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($inner -and (Test-Path -LiteralPath (Join-Path $inner.FullName 'plugin.json'))) {
        return $inner.FullName
    }
    return $null
}

$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null

$downloadedZip = $false
if ($ZipPath) {
    $ZipPath = (Resolve-Path -LiteralPath $ZipPath).Path
    if (-not $Version) {
        $match = [regex]::Match([System.IO.Path]::GetFileNameWithoutExtension($ZipPath), 'v?(\d+\.\d+\.\d+)')
        $Version = if ($match.Success) { $match.Groups[1].Value } else { 'local' }
    }
} else {
    $Version = $Version.TrimStart('v')
    if ($Version) {
        $releaseUrl = "https://api.github.com/repos/$Repo/releases/tags/v$Version"
    } else {
        $releaseUrl = "https://api.github.com/repos/$Repo/releases/latest"
    }
    Write-Step "Looking up Text Tools release..."
    try {
        $release = Invoke-RestMethod -Uri $releaseUrl -Headers $Headers
    } catch {
        throw "Could not read the GitHub release. Check your internet connection or pass -ZipPath. $($_.Exception.Message)"
    }
    $tag = [string]$release.tag_name
    if (-not $Version) { $Version = $tag.TrimStart('v') }
    $asset = $release.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
    if (-not $asset) {
        throw "Release $tag has no .zip asset."
    }
    $ZipPath = Join-Path $env:TEMP ("TextTools-{0}.zip" -f $Version)
    Write-Step "Downloading $($asset.name)..."
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ZipPath -UseBasicParsing
    $downloadedZip = $true
}

if (-not $Version) { $Version = 'unknown' }

$target = Join-Path $InstallRoot ("Text Tools-{0}" -f $Version)
$existing = @(Get-PluginFolders $InstallRoot)
$flow = Get-Process -Name 'Flow.Launcher' -ErrorAction SilentlyContinue
$wasRunning = $null -ne $flow

if ($wasRunning) {
    Write-Step "Stopping Flow Launcher..."
    $flow | Stop-Process -Force
    Start-Sleep -Milliseconds 800
}

if ($existing.Count -gt 0) {
    $backupRoot = Join-Path $env:APPDATA 'FlowLauncher\PluginBackups'
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    foreach ($folder in $existing) {
        $backup = Join-Path $backupRoot ("{0}-{1}" -f $folder.Name, $stamp)
        Write-Step "Backing up $($folder.Name)..."
        Move-Item -LiteralPath $folder.FullName -Destination $backup -Force
    }
}

Write-Step "Extracting into $target..."
if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
Expand-Archive -LiteralPath $ZipPath -DestinationPath $target -Force

$pluginRoot = Find-PluginRoot $target
if (-not $pluginRoot) {
    throw "The downloaded archive does not contain a Flow Launcher plugin (plugin.json missing)."
}
if ($pluginRoot -ne $target) {
    # Flatten a single top-level folder inside the archive.
    Get-ChildItem -LiteralPath $pluginRoot -Force | Move-Item -Destination $target -Force
    Remove-Item -LiteralPath $pluginRoot -Recurse -Force
}
if (-not (Test-Path -LiteralPath (Join-Path $target 'main.py'))) {
    throw "The downloaded archive does not contain main.py."
}

if ($downloadedZip) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
}

if ($wasRunning -and -not $NoRestart) {
    $flowExe = Join-Path $env:LOCALAPPDATA 'FlowLauncher\Flow.Launcher.exe'
    if (Test-Path -LiteralPath $flowExe) {
        Write-Step "Restarting Flow Launcher..."
        Start-Process -FilePath $flowExe
    }
}

Write-Host ""
Write-Host "Text Tools $Version installed." -ForegroundColor Green
Write-Host "Location: $target"
Write-Host "Type 'tt' in Flow Launcher to start using it."
