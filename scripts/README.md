# Obsidian MCP Server Deployment Scripts

These scripts configure Claude Code and Claude Desktop to connect to your remote Obsidian vault via the MCP (Model Context Protocol) server.

## Prerequisites

1. **Tailscale** - Connected to the same network as the Obsidian Docker host
2. **uv/uvx** - Python package runner (installed automatically by scripts)
3. **API Key** - From Obsidian's Local REST API plugin

## Getting Your API Key

1. Open Obsidian web UI: `https://obsidian.lucasdziura.art`
2. Go to **Settings → Community Plugins → Local REST API**
3. Copy the **API Key** (or generate a new one)

## Quick Setup

### Windows (PowerShell)

```powershell
# Basic setup (will prompt for API key)
.\setup-obsidian-mcp.ps1

# With API key and save to environment variable
.\setup-obsidian-mcp.ps1 -ApiKey "your_api_key" -SetEnvVar

# Also configure Claude Desktop
.\setup-obsidian-mcp.ps1 -ApiKey "your_api_key" -SetEnvVar -UseClaudeDesktop
```

### Linux/macOS (Bash)

```bash
# Make executable
chmod +x setup-obsidian-mcp.sh

# Basic setup (will prompt for API key)
./setup-obsidian-mcp.sh

# With API key and save to shell rc file
./setup-obsidian-mcp.sh --api-key "your_api_key" --set-env

# Also configure Claude Desktop
./setup-obsidian-mcp.sh --api-key "your_api_key" --set-env --claude-desktop
```

## Manual Configuration

If you prefer manual setup, add this to your configuration files:

### Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["mcp-obsidian"],
      "env": {
        "OBSIDIAN_API_KEY": "${OBSIDIAN_API_KEY}",
        "OBSIDIAN_HOST": "obsidian-api.lucasdziura.art",
        "OBSIDIAN_PORT": "443",
        "OBSIDIAN_HTTPS": "true"
      }
    }
  }
}
```

### Claude Desktop

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

Same JSON structure as above.

### Environment Variable

```bash
# Linux/macOS (~/.bashrc or ~/.zshrc)
export OBSIDIAN_API_KEY="your_api_key_here"

# Windows (PowerShell)
[System.Environment]::SetEnvironmentVariable('OBSIDIAN_API_KEY', 'your_key', 'User')
```

## Verification

1. Start Claude Code: `claude`
2. Check MCP status: `/mcp`
3. Look for `obsidian` in the connected servers list
4. Test with: "List files in my Obsidian vault"

## Available MCP Tools

Once connected, Claude has access to:

| Tool | Description |
|------|-------------|
| `list_files_in_vault` | List all files in the vault |
| `list_files_in_dir` | List files in a specific directory |
| `get_file_contents` | Read a note's content |
| `simple_search` | Search vault by text |
| `append_content` | Add content to end of a note |
| `patch_content` | Insert content at specific location |
| `delete_file` | Delete a note |

## Troubleshooting

### "Connection refused" or timeout
- Verify Tailscale is connected: `tailscale status`
- Test API directly: `curl https://obsidian-api.lucasdziura.art/`

### "401 Unauthorized"
- API key is incorrect or expired
- Regenerate in Obsidian: Settings → Local REST API

### MCP server not starting
- Ensure uvx is installed: `uvx --version`
- Test manually:
  ```bash
  OBSIDIAN_API_KEY="your_key" OBSIDIAN_HOST="obsidian-api.lucasdziura.art" OBSIDIAN_PORT="443" OBSIDIAN_HTTPS="true" uvx mcp-obsidian
  ```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Your Machine                                 │
│  ┌─────────────────┐    stdio     ┌───────────────────────────┐ │
│  │   Claude Code   │◄────────────►│   mcp-obsidian (local)    │ │
│  └─────────────────┘              └─────────────┬─────────────┘ │
└─────────────────────────────────────────────────┼───────────────┘
                                                  │ HTTPS/Tailscale
                                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Host                                   │
│  obsidian-api.lucasdziura.art → Caddy → Obsidian REST API       │
└─────────────────────────────────────────────────────────────────┘
```

The MCP server runs locally on your machine but connects to the remote Obsidian REST API over Tailscale's encrypted network.
