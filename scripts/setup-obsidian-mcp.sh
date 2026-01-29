#!/bin/bash
# Obsidian MCP Server Setup for Claude Code (Linux/macOS)
# Run this script to configure the Obsidian MCP server

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}=====================================${NC}"
echo -e "${CYAN} Obsidian MCP Server Setup for Claude${NC}"
echo -e "${CYAN}=====================================${NC}"
echo ""

# Parse arguments
API_KEY="${OBSIDIAN_API_KEY:-}"
SET_ENV_VAR=false
USE_CLAUDE_DESKTOP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --api-key)
            API_KEY="$2"
            shift 2
            ;;
        --set-env)
            SET_ENV_VAR=true
            shift
            ;;
        --claude-desktop)
            USE_CLAUDE_DESKTOP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Tailscale
if command -v tailscale &> /dev/null; then
    if tailscale status &> /dev/null; then
        echo -e "${GREEN}[OK] Tailscale is connected${NC}"
    else
        echo -e "${YELLOW}[WARN] Tailscale is installed but may not be connected${NC}"
    fi
else
    echo -e "${YELLOW}[WARN] Tailscale not found. Ensure you're connected to the Tailscale network.${NC}"
fi

# Check uv/uvx
if command -v uvx &> /dev/null; then
    echo -e "${GREEN}[OK] uvx is installed at: $(which uvx)${NC}"
else
    echo -e "${RED}[MISSING] uvx not found. Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the new path
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uvx &> /dev/null; then
        echo -e "${GREEN}[OK] uv installed successfully${NC}"
    else
        echo -e "${RED}[ERROR] Failed to install uv. Please install manually.${NC}"
        exit 1
    fi
fi

# Test connectivity
echo ""
echo -e "${YELLOW}Testing connectivity to Obsidian API...${NC}"
if curl -s --head --connect-timeout 5 "https://obsidian-api.lucasdziura.art/" > /dev/null 2>&1; then
    echo -e "${GREEN}[OK] Obsidian API is reachable${NC}"
else
    echo -e "${YELLOW}[WARN] Could not reach Obsidian API. Check Tailscale connection.${NC}"
fi

# Handle API key
echo ""
if [ -z "$API_KEY" ]; then
    echo -e "${YELLOW}No API key provided.${NC}"
    echo -e "${CYAN}Get your API key from: https://obsidian.lucasdziura.art${NC}"
    echo -e "${CYAN}Settings -> Community Plugins -> Local REST API -> API Key${NC}"
    echo ""
    read -p "Enter your Obsidian API key (or press Enter to use env var later): " API_KEY
fi

# Set environment variable
if [ "$SET_ENV_VAR" = true ] && [ -n "$API_KEY" ]; then
    echo -e "${YELLOW}Setting OBSIDIAN_API_KEY environment variable...${NC}"

    # Detect shell
    SHELL_RC=""
    if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        # Remove existing entry if present
        grep -v "export OBSIDIAN_API_KEY=" "$SHELL_RC" > "$SHELL_RC.tmp" 2>/dev/null || true
        mv "$SHELL_RC.tmp" "$SHELL_RC"

        # Add new entry
        echo "export OBSIDIAN_API_KEY=\"$API_KEY\"" >> "$SHELL_RC"
        echo -e "${GREEN}[OK] Added to $SHELL_RC${NC}"

        export OBSIDIAN_API_KEY="$API_KEY"
    fi
fi

# Generate config JSON
if [ -n "$API_KEY" ]; then
    API_KEY_VALUE="$API_KEY"
else
    API_KEY_VALUE='\${OBSIDIAN_API_KEY}'
fi

MCP_CONFIG=$(cat << EOF
{
  "obsidian": {
    "command": "uvx",
    "args": ["mcp-obsidian"],
    "env": {
      "OBSIDIAN_API_KEY": "$API_KEY_VALUE",
      "OBSIDIAN_HOST": "obsidian-api.lucasdziura.art",
      "OBSIDIAN_PORT": "443",
      "OBSIDIAN_HTTPS": "true"
    }
  }
}
EOF
)

# Claude Code configuration
echo ""
echo -e "${YELLOW}Configuring Claude Code...${NC}"

CLAUDE_JSON="$HOME/.claude.json"

if [ -f "$CLAUDE_JSON" ]; then
    # Use jq if available, otherwise use Python
    if command -v jq &> /dev/null; then
        # Merge configuration with jq
        jq --argjson mcp "$MCP_CONFIG" '.mcpServers = (.mcpServers // {}) + $mcp' "$CLAUDE_JSON" > "$CLAUDE_JSON.tmp"
        mv "$CLAUDE_JSON.tmp" "$CLAUDE_JSON"
    elif command -v python3 &> /dev/null; then
        python3 << PYEOF
import json

with open('$CLAUDE_JSON', 'r') as f:
    config = json.load(f)

mcp_config = json.loads('''$MCP_CONFIG''')

if 'mcpServers' not in config:
    config['mcpServers'] = {}
config['mcpServers'].update(mcp_config)

with open('$CLAUDE_JSON', 'w') as f:
    json.dump(config, f, indent=2)
PYEOF
    else
        echo -e "${RED}[ERROR] Neither jq nor python3 available. Please install one.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[OK] Updated $CLAUDE_JSON${NC}"
else
    echo "{\"mcpServers\": $MCP_CONFIG}" > "$CLAUDE_JSON"
    echo -e "${GREEN}[OK] Created $CLAUDE_JSON${NC}"
fi

# Claude Desktop configuration (optional)
if [ "$USE_CLAUDE_DESKTOP" = true ]; then
    echo ""
    echo -e "${YELLOW}Configuring Claude Desktop...${NC}"

    # Detect OS for config path
    if [[ "$OSTYPE" == "darwin"* ]]; then
        CLAUDE_DESKTOP_DIR="$HOME/Library/Application Support/Claude"
    else
        CLAUDE_DESKTOP_DIR="$HOME/.config/Claude"
    fi

    CLAUDE_DESKTOP_CONFIG="$CLAUDE_DESKTOP_DIR/claude_desktop_config.json"

    mkdir -p "$CLAUDE_DESKTOP_DIR"

    if [ -f "$CLAUDE_DESKTOP_CONFIG" ]; then
        if command -v jq &> /dev/null; then
            jq --argjson mcp "$MCP_CONFIG" '.mcpServers = (.mcpServers // {}) + $mcp' "$CLAUDE_DESKTOP_CONFIG" > "$CLAUDE_DESKTOP_CONFIG.tmp"
            mv "$CLAUDE_DESKTOP_CONFIG.tmp" "$CLAUDE_DESKTOP_CONFIG"
        elif command -v python3 &> /dev/null; then
            python3 << PYEOF
import json

with open('$CLAUDE_DESKTOP_CONFIG', 'r') as f:
    config = json.load(f)

mcp_config = json.loads('''$MCP_CONFIG''')

if 'mcpServers' not in config:
    config['mcpServers'] = {}
config['mcpServers'].update(mcp_config)

with open('$CLAUDE_DESKTOP_CONFIG', 'w') as f:
    json.dump(config, f, indent=2)
PYEOF
        fi
    else
        echo "{\"mcpServers\": $MCP_CONFIG}" > "$CLAUDE_DESKTOP_CONFIG"
    fi

    echo -e "${GREEN}[OK] Updated $CLAUDE_DESKTOP_CONFIG${NC}"
    echo -e "${YELLOW}[INFO] Restart Claude Desktop to apply changes${NC}"
fi

# Summary
echo ""
echo -e "${CYAN}=====================================${NC}"
echo -e "${CYAN} Setup Complete!${NC}"
echo -e "${CYAN}=====================================${NC}"
echo ""
echo -e "Configuration:"
echo -e "  Host: obsidian-api.lucasdziura.art"
echo -e "  Port: 443 (HTTPS)"
echo -e "  MCP Package: mcp-obsidian (via uvx)"
echo ""

if [ -z "$API_KEY" ] && [ -z "$OBSIDIAN_API_KEY" ]; then
    echo -e "${YELLOW}IMPORTANT: Set your API key before using:${NC}"
    echo -e "  export OBSIDIAN_API_KEY=\"your_api_key_here\""
    echo -e "  Or run this script with: --api-key 'your_key' --set-env"
    echo ""
fi

echo -e "To verify in Claude Code:"
echo -e "  1. Start Claude Code: claude"
echo -e "  2. Check MCP status: /mcp"
echo -e "  3. Test: 'List files in my Obsidian vault'"
