# Obsidian MCP Server Setup for Claude Code (Windows)
# Run this script in PowerShell to configure the Obsidian MCP server

param(
    [string]$ApiKey = $env:OBSIDIAN_API_KEY,
    [switch]$SkipEnvVar,
    [switch]$UseClaudeDesktop
)

$Host.UI.RawUI.WindowTitle = "Obsidian MCP Setup"

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " Obsidian MCP Server Setup for Claude" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check Tailscale
$tailscaleStatus = Get-Process -Name "tailscale*" -ErrorAction SilentlyContinue
if ($tailscaleStatus) {
    Write-Host "[OK] Tailscale is running" -ForegroundColor Green
} else {
    Write-Host "[WARN] Tailscale may not be running. Ensure you're connected to the Tailscale network." -ForegroundColor Yellow
}

# Check uv/uvx
$uvxPath = Get-Command uvx -ErrorAction SilentlyContinue
if ($uvxPath) {
    Write-Host "[OK] uvx is installed at: $($uvxPath.Source)" -ForegroundColor Green
} else {
    Write-Host "[MISSING] uvx not found. Installing uv..." -ForegroundColor Red
    Write-Host "Running: irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Gray
    Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# Test connectivity to Obsidian API
Write-Host ""
Write-Host "Testing connectivity to Obsidian API..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "https://obsidian-api.lucasdziura.art/" -Method Head -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] Obsidian API is reachable" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Could not reach Obsidian API. Check Tailscale connection." -ForegroundColor Yellow
}

# Handle API key
Write-Host ""
if (-not $ApiKey) {
    Write-Host "No API key provided." -ForegroundColor Yellow
    Write-Host "Get your API key from: https://obsidian.lucasdziura.art" -ForegroundColor Cyan
    Write-Host "Settings -> Community Plugins -> Local REST API -> API Key" -ForegroundColor Cyan
    Write-Host ""
    $ApiKey = Read-Host "Enter your Obsidian API key (or press Enter to use env var later)"
}

# Set environment variable by default when API key is provided (skip with -SkipEnvVar)
if ($ApiKey -and -not $SkipEnvVar) {
    Write-Host "Setting OBSIDIAN_API_KEY environment variable..." -ForegroundColor Yellow
    [System.Environment]::SetEnvironmentVariable('OBSIDIAN_API_KEY', $ApiKey, 'User')
    $env:OBSIDIAN_API_KEY = $ApiKey
    Write-Host "[OK] Environment variable set (User scope)" -ForegroundColor Green
}

# Claude Code configuration
Write-Host ""
Write-Host "Configuring Claude Code..." -ForegroundColor Yellow

$claudeJsonPath = Join-Path $env:USERPROFILE ".claude.json"

# Build the obsidian MCP config as a PSCustomObject for JSON serialization
$obsidianConfig = [PSCustomObject]@{
    command = "uvx"
    args = @("mcp-obsidian")
    env = [PSCustomObject]@{
        OBSIDIAN_API_KEY = if ($ApiKey) { $ApiKey } else { '${OBSIDIAN_API_KEY}' }
        OBSIDIAN_HOST = "obsidian-api.lucasdziura.art"
        OBSIDIAN_PORT = "443"
        OBSIDIAN_HTTPS = "true"
    }
}

if (Test-Path $claudeJsonPath) {
    $existingConfig = Get-Content $claudeJsonPath -Raw | ConvertFrom-Json

    if (-not $existingConfig.mcpServers) {
        $existingConfig | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
    }

    # Add or update the obsidian property
    if ($existingConfig.mcpServers.PSObject.Properties["obsidian"]) {
        $existingConfig.mcpServers.obsidian = $obsidianConfig
    } else {
        $existingConfig.mcpServers | Add-Member -NotePropertyName "obsidian" -NotePropertyValue $obsidianConfig
    }

    $existingConfig | ConvertTo-Json -Depth 10 | Set-Content $claudeJsonPath -Encoding UTF8
    Write-Host "[OK] Updated $claudeJsonPath" -ForegroundColor Green
} else {
    [PSCustomObject]@{ mcpServers = [PSCustomObject]@{ obsidian = $obsidianConfig } } | ConvertTo-Json -Depth 10 | Set-Content $claudeJsonPath -Encoding UTF8
    Write-Host "[OK] Created $claudeJsonPath" -ForegroundColor Green
}

# Claude Desktop configuration (optional)
if ($UseClaudeDesktop) {
    Write-Host ""
    Write-Host "Configuring Claude Desktop..." -ForegroundColor Yellow

    $claudeDesktopPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    $claudeDesktopDir = Split-Path $claudeDesktopPath -Parent

    if (-not (Test-Path $claudeDesktopDir)) {
        New-Item -ItemType Directory -Path $claudeDesktopDir -Force | Out-Null
    }

    if (Test-Path $claudeDesktopPath) {
        $desktopConfig = Get-Content $claudeDesktopPath -Raw | ConvertFrom-Json
        if (-not $desktopConfig.mcpServers) {
            $desktopConfig | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
        }

        if ($desktopConfig.mcpServers.PSObject.Properties["obsidian"]) {
            $desktopConfig.mcpServers.obsidian = $obsidianConfig
        } else {
            $desktopConfig.mcpServers | Add-Member -NotePropertyName "obsidian" -NotePropertyValue $obsidianConfig
        }
        $desktopConfig | ConvertTo-Json -Depth 10 | Set-Content $claudeDesktopPath -Encoding UTF8
    } else {
        [PSCustomObject]@{ mcpServers = [PSCustomObject]@{ obsidian = $obsidianConfig } } | ConvertTo-Json -Depth 10 | Set-Content $claudeDesktopPath -Encoding UTF8
    }
    Write-Host "[OK] Updated $claudeDesktopPath" -ForegroundColor Green
    Write-Host "[INFO] Restart Claude Desktop to apply changes" -ForegroundColor Yellow
}

# Install /obsidian skill
Write-Host ""
Write-Host "Installing /obsidian skill..." -ForegroundColor Yellow

$skillSource = Join-Path $PSScriptRoot "..\skills\obsidian\SKILL.md"
$skillDestDir = Join-Path $env:USERPROFILE ".claude\skills\obsidian"
$skillDest = Join-Path $skillDestDir "SKILL.md"

if (Test-Path $skillSource) {
    if (-not (Test-Path $skillDestDir)) {
        New-Item -ItemType Directory -Path $skillDestDir -Force | Out-Null
    }
    Copy-Item -Path $skillSource -Destination $skillDest -Force
    Write-Host "[OK] Installed /obsidian skill to $skillDest" -ForegroundColor Green
} else {
    Write-Host "[WARN] Skill file not found at $skillSource - skipping skill install" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " Setup Complete!" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor White
Write-Host "  Host: obsidian-api.lucasdziura.art" -ForegroundColor Gray
Write-Host "  Port: 443 (HTTPS)" -ForegroundColor Gray
Write-Host "  MCP Package: mcp-obsidian (via uvx)" -ForegroundColor Gray
Write-Host "  Skill: /obsidian (folder reader)" -ForegroundColor Gray
Write-Host ""

if (-not $ApiKey -and -not $env:OBSIDIAN_API_KEY) {
    Write-Host "IMPORTANT: Set your API key before using:" -ForegroundColor Yellow
    Write-Host "  Run this script with: -ApiKey 'your_key'" -ForegroundColor White
    Write-Host "  (Environment variable will be set automatically)" -ForegroundColor White
    Write-Host ""
}

Write-Host "To verify in Claude Code:" -ForegroundColor White
Write-Host "  1. Start Claude Code: claude" -ForegroundColor Gray
Write-Host "  2. Check MCP status: /mcp" -ForegroundColor Gray
Write-Host "  3. Test: 'List files in my Obsidian vault'" -ForegroundColor Gray
