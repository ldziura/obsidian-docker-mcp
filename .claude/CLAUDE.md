# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Self-hosted Obsidian stack providing browser-accessible Obsidian with secure remote access via Tailscale, automatic HTTPS via Caddy, and cross-device sync via Cloudflare R2.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                      │
├─────────────────────────────────────────────────────────────┤
│  ofelia          - Scheduled jobs (backups, restarts)       │
│  tailscale       - Secure network access (VPN)              │
│  caddy           - Reverse proxy with auto HTTPS            │
│  obsidian        - LinuxServer.io Obsidian (KasmVNC web UI) │
└─────────────────────────────────────────────────────────────┘

External:
- Cloudflare R2: Vault sync via Remotely Save plugin
- Cloudflare DNS: DNS challenge for TLS certificates
- Tailscale: Private network access
```

**Network Flow:** Internet → Tailscale → Caddy (HTTPS) → Obsidian (port 3000)

## Common Commands

```bash
# Start/stop stack
docker compose up -d
docker compose down

# View logs
docker compose logs -f obsidian
docker compose logs -f obsidian-ofelia

# Check Tailscale status
docker exec obsidian-tailscale tailscale status
docker exec obsidian-tailscale tailscale ip -4

# Manual vault backup
docker exec obsidian sh -c 'tar -czf /config/backups/vault-manual-$(date +%Y%m%d-%H%M%S).tar.gz -C /vault .'

# List backups
docker exec obsidian ls -la /config/backups/

# Enter container shell
docker exec -it obsidian bash
```

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Service definitions (ofelia, tailscale, caddy, obsidian) |
| `Caddyfile` | Reverse proxy config for `obsidian.lucasdziura.art` |
| `.env` | Secrets (TS_AUTHKEY, CLOUDFLARE_API_TOKEN, OBSIDIAN_PASSWORD) |
| `vault/` | Obsidian vault (PARA structure) |
| `vault/CLAUDE.md` | Vault-specific context for working with notes |
| `obsidian-config/` | Obsidian app config and backups |

## Scheduled Jobs (Ofelia)

| Schedule | Job | Action |
|----------|-----|--------|
| 3:00 AM daily | backup | Backup vault to `/config/backups/vault-YYYYMMDD-HHMMSS.tar.gz` |
| 4:00 AM daily | cleanup | Delete backups older than 7 days |
| 4:00 AM Sunday | restart | Restart Obsidian (Electron memory management) |

## Environment Variables

Required in `.env` (see `.env.example`):
- `TS_AUTHKEY` - Tailscale auth key
- `CLOUDFLARE_API_TOKEN` - For DNS challenge TLS certs
- `OBSIDIAN_PASSWORD` - Web UI password

Optional R2 config (used by Remotely Save plugin, not Docker):
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`

## Access URLs

- Web UI: `https://obsidian.lucasdziura.art` (via Tailscale)
- REST API: `https://obsidian-api.lucasdziura.art` (for MCP server)
- Local HTTPS: `http://localhost:13443`
- Local REST API: `http://localhost:27124`

## Vault Structure (PARA Method)

The vault uses PARA organization. See `vault/CLAUDE.md` for detailed vault editing guidelines.

```
vault/
├── 00_Inbox/       # Quick capture
├── 01_Projects/    # Active projects
├── 02_Areas/       # Ongoing responsibilities
├── 03_Resources/   # Reference material
├── 04_Archive/     # Completed/inactive
├── daily/          # Daily notes (YYYY-MM-DD.md)
└── templates/      # Templater templates
```

## When Editing Vault Notes

Always reference `vault/CLAUDE.md` for Obsidian-specific formatting rules:
- Use `[[wikilinks]]` not markdown links
- Include YAML frontmatter with `created`, `modified`, `tags`
- Place new notes in `00_Inbox/` unless destination is clear
- Use templates from `vault/templates/`
