# Obsidian MCP Server Setup for Claude (Windows)
# Run this script in PowerShell to configure the Obsidian MCP server
# Configures both Claude Code and Claude Desktop by default

param(
    [string]$ApiKey = $env:OBSIDIAN_API_KEY,
    [switch]$SkipEnvVar,
    [switch]$SkipClaudeDesktop
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

# Resolve the repo root (scripts/ is one level down)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$canvasServerDir = Join-Path $repoRoot "mcp-servers\obsidian-canvas"

# Build shared env config
$envConfig = [PSCustomObject]@{
    OBSIDIAN_API_KEY = if ($ApiKey) { $ApiKey } else { '${OBSIDIAN_API_KEY}' }
    OBSIDIAN_HOST = "obsidian-api.lucasdziura.art"
    OBSIDIAN_PORT = "443"
    OBSIDIAN_HTTPS = "true"
}

# Resolve full paths (Claude Desktop doesn't inherit shell PATH)
$uvxFullPath = (Get-Command uvx -ErrorAction SilentlyContinue).Source
$uvFullPath = (Get-Command uv -ErrorAction SilentlyContinue).Source

# Build the obsidian MCP config as a PSCustomObject for JSON serialization
$obsidianConfig = [PSCustomObject]@{
    command = $uvxFullPath
    args = @("--from", "mcp-obsidian==0.2.1", "mcp-obsidian")
    env = $envConfig
}

# Build the obsidian-canvas MCP config (local package, uses uv --directory)
$canvasConfig = [PSCustomObject]@{
    command = $uvFullPath
    args = @("--directory", $canvasServerDir, "run", "obsidian-canvas-mcp")
    env = $envConfig
}

# Helper function to add or update an MCP server entry
function Set-McpServer($config, $name, $value) {
    if ($config.mcpServers.PSObject.Properties[$name]) {
        $config.mcpServers.$name = $value
    } else {
        $config.mcpServers | Add-Member -NotePropertyName $name -NotePropertyValue $value
    }
}

if (Test-Path $claudeJsonPath) {
    $existingConfig = Get-Content $claudeJsonPath -Raw | ConvertFrom-Json

    if (-not $existingConfig.mcpServers) {
        $existingConfig | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
    }

    Set-McpServer $existingConfig "obsidian" $obsidianConfig
    Set-McpServer $existingConfig "obsidian-canvas" $canvasConfig

    $existingConfig | ConvertTo-Json -Depth 10 | Set-Content $claudeJsonPath -Encoding UTF8
    Write-Host "[OK] Updated $claudeJsonPath" -ForegroundColor Green
} else {
    [PSCustomObject]@{
        mcpServers = [PSCustomObject]@{
            obsidian = $obsidianConfig
            "obsidian-canvas" = $canvasConfig
        }
    } | ConvertTo-Json -Depth 10 | Set-Content $claudeJsonPath -Encoding UTF8
    Write-Host "[OK] Created $claudeJsonPath" -ForegroundColor Green
}

# Claude Desktop configuration (default, skip with -SkipClaudeDesktop)
if (-not $SkipClaudeDesktop) {
    Write-Host ""
    Write-Host "Configuring Claude Desktop..." -ForegroundColor Yellow

    # Detect config path: Microsoft Store vs standard installer
    $storeConfigDir = Join-Path $env:LOCALAPPDATA "Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude"
    $standardConfigDir = Join-Path $env:APPDATA "Claude"

    if (Test-Path $storeConfigDir) {
        $claudeDesktopDir = $storeConfigDir
        Write-Host "[INFO] Detected Microsoft Store installation" -ForegroundColor Cyan
    } elseif (Test-Path $standardConfigDir) {
        $claudeDesktopDir = $standardConfigDir
        Write-Host "[INFO] Detected standard installation" -ForegroundColor Cyan
    } else {
        # Default to standard path and create it
        $claudeDesktopDir = $standardConfigDir
        New-Item -ItemType Directory -Path $claudeDesktopDir -Force | Out-Null
        Write-Host "[INFO] Created config directory at standard path" -ForegroundColor Cyan
    }

    $claudeDesktopPath = Join-Path $claudeDesktopDir "claude_desktop_config.json"

    if (Test-Path $claudeDesktopPath) {
        $desktopConfig = Get-Content $claudeDesktopPath -Raw | ConvertFrom-Json
        if (-not $desktopConfig.mcpServers) {
            $desktopConfig | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
        }

        Set-McpServer $desktopConfig "obsidian" $obsidianConfig
        Set-McpServer $desktopConfig "obsidian-canvas" $canvasConfig

        $desktopConfig | ConvertTo-Json -Depth 10 | Set-Content $claudeDesktopPath -Encoding UTF8
    } else {
        [PSCustomObject]@{
            mcpServers = [PSCustomObject]@{
                obsidian = $obsidianConfig
                "obsidian-canvas" = $canvasConfig
            }
        } | ConvertTo-Json -Depth 10 | Set-Content $claudeDesktopPath -Encoding UTF8
    }
    Write-Host "[OK] Updated $claudeDesktopPath" -ForegroundColor Green
    Write-Host "[INFO] Restart Claude Desktop to apply changes" -ForegroundColor Yellow
}

# Install obsidian-canvas-mcp dependencies
Write-Host ""
Write-Host "Installing obsidian-canvas-mcp dependencies..." -ForegroundColor Yellow

if (Test-Path $canvasServerDir) {
    try {
        Push-Location $canvasServerDir
        & uv sync 2>&1 | Out-Null
        Pop-Location
        Write-Host "[OK] obsidian-canvas-mcp dependencies installed" -ForegroundColor Green
    } catch {
        Pop-Location
        Write-Host "[WARN] Failed to install canvas MCP dependencies: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "[WARN] Canvas MCP server not found at $canvasServerDir" -ForegroundColor Yellow
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
Write-Host "  MCP Servers:" -ForegroundColor Gray
Write-Host "    - obsidian (notes, search, files via uvx)" -ForegroundColor Gray
Write-Host "    - obsidian-canvas (canvas operations via local package)" -ForegroundColor Gray
Write-Host "  Skill: /obsidian (folder reader)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Chat tab skill:" -ForegroundColor White
Write-Host "    To use Obsidian in Claude Desktop's Chat tab:" -ForegroundColor Gray
Write-Host "    1. ZIP the skills/obsidian-chat/ folder" -ForegroundColor Gray
Write-Host "    2. Upload via Claude Desktop > Customize > Skills" -ForegroundColor Gray
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
