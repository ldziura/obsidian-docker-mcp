# Self-Hosted Obsidian with Docker and MCP Integration

A Docker Compose stack for running Obsidian in the browser with secure remote access via Tailscale, automatic HTTPS certificates, and Claude Code integration through the Model Context Protocol (MCP).

## Features

- **Browser-based Obsidian** - Access your vault from any device via KasmVNC web UI
- **Secure Remote Access** - Tailscale VPN for private, encrypted connections
- **Automatic HTTPS** - Caddy reverse proxy with Cloudflare DNS challenge
- **MCP Integration** - Claude Code can read and write to your vault
- **Automated Backups** - Daily vault backups with 7-day retention
- **Cross-device Sync** - Optional Cloudflare R2 sync via Remotely Save plugin

## Architecture

```
Internet
    |
    v
Tailscale VPN (encrypted tunnel)
    |
    v
+-------------------+     +-------------------+     +-------------------+
|     Caddy         |---->|    Obsidian       |<----|     Ofelia        |
| (reverse proxy)   |     | (LinuxServer.io)  |     | (job scheduler)   |
| - Auto HTTPS      |     | - KasmVNC web UI  |     | - Daily backups   |
| - Cloudflare DNS  |     | - REST API        |     | - Cleanup jobs    |
+-------------------+     +-------------------+     +-------------------+
```

**Services:**
| Service | Image | Purpose |
|---------|-------|---------|
| tailscale | `tailscale/tailscale` | VPN for secure network access |
| caddy | `slothcroissant/caddy-cloudflaredns` | Reverse proxy with auto HTTPS |
| obsidian | `lscr.io/linuxserver/obsidian` | Obsidian app with web UI |
| ofelia | `mcuadros/ofelia` | Cron job scheduler for backups |

## Prerequisites

- Docker and Docker Compose
- Tailscale account
- Cloudflare account with a domain
- (Optional) Cloudflare R2 bucket for vault sync

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/ldziura/obsidian-docker-mcp.git
cd obsidian-docker-mcp
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```bash
# Tailscale auth key (https://login.tailscale.com/admin/settings/keys)
TS_AUTHKEY=tskey-auth-xxxxx

# Cloudflare API token with Zone:DNS:Edit permission
CLOUDFLARE_API_TOKEN=your_token

# Password for Obsidian web UI
OBSIDIAN_PASSWORD=your_secure_password

# Optional: R2 credentials for Remotely Save plugin
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=obsidian-vault
```

### 3. Configure Caddyfile

```bash
cp Caddyfile.example Caddyfile
```

Edit `Caddyfile` and replace `example.com` with your domain:

```
obsidian.yourdomain.com {
    reverse_proxy host.docker.internal:13443
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }
}

obsidian-api.yourdomain.com {
    reverse_proxy https://host.docker.internal:27124 {
        transport http {
            tls_insecure_skip_verify
        }
    }
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }
}
```

### 4. Start the Stack

```bash
docker compose up -d
```

### 5. Access Obsidian

- **Web UI:** `https://obsidian.yourdomain.com` (via Tailscale)
- **Local:** `http://localhost:13443`
- **REST API:** `https://obsidian-api.yourdomain.com`

## MCP Integration with Claude Code

This setup enables Claude Code to read and write to your Obsidian vault using the MCP protocol.

### Setup Scripts

Run the appropriate setup script from the `scripts/` directory:

**Windows (PowerShell):**
```powershell
.\scripts\setup-obsidian-mcp.ps1 -ApiKey "your_api_key" -SetEnvVar
```

**Linux/macOS:**
```bash
./scripts/setup-obsidian-mcp.sh --api-key "your_api_key" --set-env
```

### Manual Configuration

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["mcp-obsidian"],
      "env": {
        "OBSIDIAN_API_KEY": "${OBSIDIAN_API_KEY}",
        "OBSIDIAN_HOST": "obsidian-api.yourdomain.com",
        "OBSIDIAN_PORT": "443",
        "OBSIDIAN_HTTPS": "true"
      }
    }
  }
}
```

### Getting the API Key

1. Open Obsidian web UI
2. Go to Settings > Community Plugins > Local REST API
3. Copy or generate an API Key

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `list_files_in_vault` | List all files in the vault |
| `list_files_in_dir` | List files in a specific directory |
| `get_file_contents` | Read a note's content |
| `simple_search` | Search vault by text |
| `append_content` | Add content to a note |
| `patch_content` | Insert content at a specific location |
| `delete_file` | Delete a note |

## Directory Structure

```
obsidian-docker/
├── docker-compose.yml      # Service definitions
├── Caddyfile.example       # Reverse proxy template
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore rules
├── scripts/
│   ├── setup-obsidian-mcp.ps1   # Windows MCP setup
│   └── setup-obsidian-mcp.sh    # Linux/macOS MCP setup
├── vault/                  # Your Obsidian vault (gitignored)
├── obsidian-config/        # Obsidian app config (gitignored)
├── tailscale-state/        # Tailscale auth state (gitignored)
├── caddy-data/             # TLS certificates (gitignored)
└── caddy-config/           # Caddy config state (gitignored)
```

## Automated Tasks

Ofelia runs the following scheduled jobs:

| Schedule | Job | Description |
|----------|-----|-------------|
| Daily 3:00 AM | backup | Compress vault to `/config/backups/vault-YYYYMMDD-HHMMSS.tar.gz` |
| Daily 4:00 AM | cleanup | Delete backups older than 7 days |
| Sunday 4:00 AM | restart | Restart Obsidian container for stability |

### Manual Backup

```bash
docker exec obsidian sh -c 'tar -czf /config/backups/vault-manual-$(date +%Y%m%d-%H%M%S).tar.gz -C /vault .'
```

### List Backups

```bash
docker exec obsidian ls -la /config/backups/
```

## Common Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f obsidian
docker compose logs -f caddy

# Check Tailscale status
docker exec obsidian-tailscale tailscale status

# Get Tailscale IP
docker exec obsidian-tailscale tailscale ip -4

# Enter Obsidian container
docker exec -it obsidian bash
```

## Troubleshooting

### Cannot access web UI

1. Verify Tailscale is connected: `tailscale status`
2. Check Caddy logs: `docker compose logs caddy`
3. Ensure DNS records point to your Tailscale IP

### MCP connection refused

1. Verify Tailscale connectivity: `tailscale status`
2. Test API endpoint: `curl https://obsidian-api.yourdomain.com/`
3. Check that Local REST API plugin is enabled in Obsidian

### 401 Unauthorized from MCP

1. Verify API key in environment: `echo $OBSIDIAN_API_KEY`
2. Regenerate key in Obsidian: Settings > Local REST API

### Backup job not running

1. Check Ofelia logs: `docker compose logs ofelia`
2. Verify Docker socket is mounted correctly

## Security Considerations

- All traffic is encrypted via Tailscale VPN
- HTTPS certificates are automatically provisioned via Cloudflare DNS challenge
- Sensitive files (`.env`, `Caddyfile`, `tailscale-state/`) are gitignored
- API keys should be stored as environment variables, not in config files

## License

MIT License
