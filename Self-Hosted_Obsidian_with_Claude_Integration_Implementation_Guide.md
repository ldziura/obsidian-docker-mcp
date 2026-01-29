# Self-Hosted Obsidian with Claude Integration: Implementation Guide

**Purpose:** Deploy a complete self-hosted Obsidian stack with remote web access, cross-device sync, and Claude Code integration for persistent AI-powered knowledge management.

**Architecture Overview:**
- **Remote Access:** LinuxServer.io Obsidian Docker image with Tailscale sidecar
- **Sync:** Remotely Save plugin with S3-compatible storage (Cloudflare R2)
- **Claude Integration:** Direct filesystem access + MCP server for Claude Desktop
- **Access Pattern:** `obsidian.lucasdziura.art` via Tailscale + Caddy reverse proxy

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Directory Structure](#2-directory-structure)
3. [Docker Stack Deployment](#3-docker-stack-deployment)
4. [Caddy Configuration](#4-caddy-configuration)
5. [Obsidian Initial Setup](#5-obsidian-initial-setup)
6. [Sync Configuration](#6-sync-configuration)
7. [Claude Code Integration](#7-claude-code-integration)
8. [MCP Server Setup](#8-mcp-server-setup)
9. [CLAUDE.md Configuration](#9-claudemd-configuration)
10. [Essential Plugins](#10-essential-plugins)
11. [Maintenance & Backup](#11-maintenance--backup)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

### Required
- Docker Desktop for Windows installed and running
- Tailscale account and network configured
- Domain with Cloudflare DNS (for `obsidian.lucasdziura.art`)
- Cloudflare R2 bucket (for sync) - free tier is sufficient

### Optional
- Claude Desktop installed (for MCP integration)
- Python 3.10+ with `uv` package manager (for MCP server)

### Information to Gather Before Starting

```yaml
# Fill these in before deployment
tailscale_auth_key: "tskey-auth-XXXXX"  # Generate at https://login.tailscale.com/admin/settings/keys
cloudflare_api_token: "XXXXX"            # Zone:DNS:Edit for your domain
cloudflare_r2_access_key: "XXXXX"        # For Remotely Save sync
cloudflare_r2_secret_key: "XXXXX"
cloudflare_r2_endpoint: "https://ACCOUNT_ID.r2.cloudflarestorage.com"
cloudflare_r2_bucket: "obsidian-vault"
obsidian_password: "secure_password_here"  # For web UI access
```

---

## 2. Directory Structure

Create the following directory structure (matching your existing stack patterns):

```
W:\PersonalProjects\self-hosted-stack\obsidian-docker\
├── docker-compose.yml
├── Caddyfile
├── .env
├── .env.example
├── obsidian-config/              # Obsidian app config (will contain backups folder)
│   └── backups/                  # Automated backups via Ofelia
├── vault/                        # Your Obsidian vault
│   ├── CLAUDE.md                 # Claude Code context file
│   ├── .obsidian/                # Obsidian configuration
│   ├── 00_Inbox/                 # Capture point
│   ├── 01_Projects/              # Active initiatives
│   ├── 02_Areas/                 # Ongoing responsibilities
│   ├── 03_Resources/             # Reference materials
│   ├── 04_Archive/               # Completed content
│   ├── daily/                    # Daily notes
│   └── templates/                # Note templates
├── tailscale-state/              # Tailscale persistent state
├── caddy-data/                   # Caddy certificates
└── caddy-config/                 # Caddy configuration
```

### Create Directory Structure

```powershell
# PowerShell (Windows)
$base = "W:\PersonalProjects\self-hosted-stack\obsidian-docker"
New-Item -ItemType Directory -Force -Path @(
    "$base\obsidian-config\backups",
    "$base\vault\00_Inbox",
    "$base\vault\01_Projects",
    "$base\vault\02_Areas",
    "$base\vault\03_Resources",
    "$base\vault\04_Archive",
    "$base\vault\daily",
    "$base\vault\templates",
    "$base\tailscale-state",
    "$base\caddy-data",
    "$base\caddy-config"
)
```

---

## 3. Docker Stack Deployment

### 3.1 Environment File

Create `.env`:

```env
# Tailscale auth key (get from https://login.tailscale.com/admin/settings/keys)
# Use a reusable key with appropriate tags
TS_AUTHKEY=tskey-auth-xxxxx

# Cloudflare API token (for DNS challenge TLS certs)
# Create at https://dash.cloudflare.com/profile/api-tokens
# Needs Zone:DNS:Edit permissions for your domain
CLOUDFLARE_API_TOKEN=xxxxx

# Obsidian Web UI credentials
OBSIDIAN_PASSWORD=your_secure_password
```

Create `.env.example` (for git):

```env
# Tailscale auth key (get from https://login.tailscale.com/admin/settings/keys)
# Use a reusable key with appropriate tags
TS_AUTHKEY=tskey-auth-xxxxx

# Cloudflare API token (for DNS challenge TLS certs)
# Create at https://dash.cloudflare.com/profile/api-tokens
# Needs Zone:DNS:Edit permissions for your domain
CLOUDFLARE_API_TOKEN=xxxxx

# Obsidian Web UI credentials
OBSIDIAN_PASSWORD=change_me
```

### 3.2 Docker Compose

Create `docker-compose.yml`:

```yaml
services:
  # ============================================
  # OFELIA - Job scheduler for container maintenance
  # ============================================
  ofelia:
    image: mcuadros/ofelia:latest
    container_name: obsidian-ofelia
    command: daemon --docker
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    labels:
      ofelia.enabled: "true"
      # Restart obsidian every Sunday at 4am to clear memory leaks (Electron apps)
      ofelia.job-run.restart-obsidian.schedule: "0 4 * * 0"
      ofelia.job-run.restart-obsidian.command: "restart"
      ofelia.job-run.restart-obsidian.container: "obsidian"
      # Backup vault every day at 3am
      ofelia.job-exec.backup-vault.schedule: "0 3 * * *"
      ofelia.job-exec.backup-vault.container: "obsidian"
      ofelia.job-exec.backup-vault.command: "sh -c 'tar -czf /config/backups/vault-$(date +%Y%m%d).tar.gz -C /vault . 2>/dev/null || true'"
      # Cleanup old backups every day at 4am (keep last 30 days)
      ofelia.job-exec.cleanup-backups.schedule: "0 4 * * *"
      ofelia.job-exec.cleanup-backups.container: "obsidian"
      ofelia.job-exec.cleanup-backups.command: "sh -c 'find /config/backups -name \"vault-*.tar.gz\" -mtime +30 -delete 2>/dev/null || true'"
    depends_on:
      - obsidian
    restart: unless-stopped

  # ============================================
  # TAILSCALE - Secure network access
  # Each stack gets its own Tailscale IP
  # ============================================
  tailscale:
    image: tailscale/tailscale:latest
    container_name: obsidian-tailscale
    hostname: obsidian-docker
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_STATE_DIR=/var/lib/tailscale
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./tailscale-state:/var/lib/tailscale
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - NET_ADMIN
      - NET_RAW
    restart: unless-stopped

  # ============================================
  # CADDY - HTTPS reverse proxy
  # Runs in Tailscale's network namespace
  # Binds to 80/443 on Tailscale IP, not host
  # ============================================
  caddy:
    image: slothcroissant/caddy-cloudflaredns:latest
    container_name: obsidian-caddy
    network_mode: service:tailscale
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./caddy-data:/data
      - ./caddy-config:/config
    environment:
      - CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN}
    depends_on:
      - tailscale
    restart: unless-stopped

  # ============================================
  # OBSIDIAN - Browser-accessible via KasmVNC
  # LinuxServer.io image with Selkies streaming
  # ============================================
  obsidian:
    image: lscr.io/linuxserver/obsidian:latest
    container_name: obsidian
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Montreal
      - CUSTOM_USER=lucas
      - PASSWORD=${OBSIDIAN_PASSWORD}
      # Docker Mods for additional functionality
      - DOCKER_MODS=linuxserver/mods:universal-git
    volumes:
      - ./obsidian-config:/config
      - ./vault:/vault
    ports:
      # Only HTTPS exposed - HTTP (3000) intentionally not exposed for security
      # Credentials are transmitted over this connection
      # Using uncommon port 13443 to avoid conflicts
      - "13443:3001"
      # REST API for Local REST API plugin (MCP server access)
      - "27124:27124"
    # Critical: Electron apps need shared memory
    shm_size: "1gb"
    # Security options for Electron
    security_opt:
      - seccomp:unconfined
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 3.3 Deploy the Stack

```bash
cd W:\PersonalProjects\self-hosted-stack\obsidian-docker
docker compose up -d

# Verify containers are running
docker compose ps

# Check logs for any issues
docker compose logs -f obsidian
docker compose logs -f obsidian-tailscale
```

### 3.4 Verify Tailscale Connection

```bash
# Check Tailscale status
docker exec obsidian-tailscale tailscale status

# Get the Tailscale IP
docker exec obsidian-tailscale tailscale ip -4
```

Note the Tailscale IP (e.g., `100.x.y.z`) - you'll need this for Cloudflare DNS.

---

## 4. Caddyfile Configuration

Create `Caddyfile`:

```caddyfile
# Obsidian Web UI (HTTPS - secure streaming)
obsidian.lucasdziura.art {
    reverse_proxy host.docker.internal:13443 {
        transport http {
            tls_insecure_skip_verify
        }
    }

    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }
}

# Obsidian REST API (for MCP server access from other machines)
# Only needed if you want Claude Desktop on another machine to access
obsidian-api.lucasdziura.art {
    reverse_proxy host.docker.internal:27124

    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }
}
```

**Security Note:** We only expose port 13443 (mapped from container's 3001/HTTPS) - the HTTP port 3000 is intentionally not exposed to avoid unencrypted credential transmission. The `tls_insecure_skip_verify` is safe here because it's internal container-to-container communication (the container's self-signed cert); Caddy still serves valid HTTPS to external clients via Cloudflare DNS challenge.

### DNS Setup in Cloudflare

After getting your Tailscale IP (`docker exec obsidian-tailscale tailscale ip -4`), create A records:

| Name | Type | Content | Proxy |
|------|------|---------|-------|
| obsidian | A | 100.x.y.z | DNS only (grey cloud) |
| obsidian-api | A | 100.x.y.z | DNS only (grey cloud) |

**Important:** Use "DNS only" (grey cloud), not "Proxied" - Tailscale handles the security.

---

## 5. Obsidian Initial Setup

### 5.1 Access Obsidian Web UI

1. Navigate to `https://obsidian.lucasdziura.art` (after DNS propagates)
   - Or use local access: `https://localhost:13443` (accept self-signed cert warning)
2. Login with the credentials from `.env` (user: `lucas`, password: your configured password)
3. On first launch, Obsidian will ask to create/open a vault

### 5.2 Create or Open Vault

1. Click "Open folder as vault"
2. Navigate to `/vault` (this is the mounted volume)
3. Select it as your vault location

### 5.3 Configure Obsidian Settings

Navigate to Settings (gear icon) and configure:

**Editor:**
- Default editing mode: Live Preview
- Spell check: Enable
- Auto pair brackets: Enable

**Files & Links:**
- Automatically update internal links: Enable
- Default location for new notes: `00_Inbox`
- New link format: Relative path to file
- Use [[Wikilinks]]: Enable

**Appearance:**
- Base theme: Dark (or preference)
- Install a community theme if desired

---

## 6. Sync Configuration

### 6.1 Set Up Cloudflare R2 Bucket

1. Log into Cloudflare Dashboard
2. Navigate to R2 Object Storage
3. Create a new bucket named `obsidian-vault`
4. Generate R2 API Token:
   - Go to R2 > Overview > Manage R2 API Tokens
   - Create token with "Object Read & Write" permissions
   - Note the Access Key ID and Secret Access Key

### 6.2 Install Remotely Save Plugin

1. In Obsidian, go to Settings > Community plugins
2. Disable Safe mode if prompted
3. Browse community plugins
4. Search for "Remotely Save"
5. Install and Enable

### 6.3 Configure Remotely Save

1. Go to Settings > Remotely Save
2. Configure S3-compatible storage:

```
Choose Service: S3 or compatible

S3 Endpoint: https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
S3 Region: auto
S3 Access Key ID: [Your R2 Access Key]
S3 Secret Access Key: [Your R2 Secret Key]
S3 Bucket Name: obsidian-vault

Enable: Check sync on startup
Enable: Check sync on save (after 10 seconds)
```

3. Click "Check Connectivity" to verify
4. Click "Sync" to perform initial sync

### 6.4 Configure Other Devices

On each additional device:
1. Install Obsidian
2. Create empty vault at same location
3. Install Remotely Save plugin
4. Configure with same R2 credentials
5. Sync to pull down all content

---

## 7. Claude Code Integration

### 7.1 Add Vault to Allowed Directories

Claude Code needs filesystem access to your vault. Since you're syncing with Remotely Save, you have two options:

**Option A: Access synced local vault (recommended for daily use)**

Your vault syncs to a local path via Remotely Save. Create a dedicated local vault location:
- Windows: `C:\Users\Lucas\Documents\ObsidianVault`
- Or symlink to Docker volume: Create junction to `W:\PersonalProjects\self-hosted-stack\obsidian-docker\vault`

```powershell
# Create junction (Windows symlink for directories)
New-Item -ItemType Junction -Path "C:\Users\Lucas\Documents\ObsidianVault" -Target "W:\PersonalProjects\self-hosted-stack\obsidian-docker\vault"
```

**Option B: Access Docker volume directly (same machine as Docker)**

If Claude Code runs on the same machine as Docker, access the vault directly:
```
W:\PersonalProjects\self-hosted-stack\obsidian-docker\vault
```

### 7.2 Working with Claude Code

```powershell
# Navigate to your vault
cd W:\PersonalProjects\self-hosted-stack\obsidian-docker\vault

# Start Claude Code
claude

# Claude now has full read/write access to your vault
```

### 7.3 Useful Claude Code Commands for Obsidian

```bash
# Search vault content
claude "Search my vault for notes about Japanese learning"

# Create a new note
claude "Create a new project note for my LLM inference server"

# Summarize recent daily notes
claude "Summarize my daily notes from the past week"

# Organize inbox
claude "Review my 00_Inbox folder and suggest organization"

# Generate connections
claude "Find connections between my recent notes and suggest links"
```

---

## 8. MCP Server Setup

For Claude Desktop integration, set up the MCP server.

### 8.1 Install Prerequisites

```bash
# Install uv package manager if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
uv --version
```

### 8.2 Install Obsidian Local REST API Plugin

1. In Obsidian, go to Settings > Community plugins
2. Search for "Local REST API"
3. Install and Enable
4. Go to the plugin settings
5. Note the API Key (you'll need this)
6. Default port is 27124

### 8.3 Configure Claude Desktop

Edit your Claude Desktop configuration:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["mcp-obsidian"],
      "env": {
        "OBSIDIAN_API_KEY": "your_api_key_from_plugin",
        "OBSIDIAN_HOST": "127.0.0.1",
        "OBSIDIAN_PORT": "27124"
      }
    }
  }
}
```

### 8.4 Verify MCP Connection

1. Restart Claude Desktop
2. Start a new conversation
3. You should see "obsidian" listed as an available tool
4. Test with: "List the notes in my vault"

### 8.5 Alternative: cyanheads MCP Server (Better Performance)

For larger vaults, use the cyanheads server with caching:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "npx",
      "args": ["-y", "obsidian-mcp-server"],
      "env": {
        "OBSIDIAN_API_KEY": "your_api_key_from_plugin",
        "OBSIDIAN_HOST": "127.0.0.1",
        "OBSIDIAN_PORT": "27124"
      }
    }
  }
}
```

---

## 9. CLAUDE.md Configuration

Create `vault/CLAUDE.md` (this goes in the root of your vault):

```markdown
# Obsidian Vault Context for Claude

## Vault Overview

This is Lucas's personal knowledge management vault, using a modified PARA organization system. The vault serves as a second brain for projects, learning (especially Japanese), and technical documentation.

## Directory Structure

```
/vault
├── 00_Inbox/          # Capture point - new notes land here
├── 01_Projects/       # Active, time-bound initiatives with clear outcomes
├── 02_Areas/          # Ongoing responsibilities (Japanese learning, homelab, work)
├── 03_Resources/      # Reference materials, snippets, documentation
├── 04_Archive/        # Completed or inactive content
├── daily/             # Daily notes (YYYY-MM-DD.md format)
└── templates/         # Note templates for consistent formatting
```

## Obsidian Formatting Rules

### Links
- Always use `[[wikilinks]]` for internal links, never markdown `[text](url)` format
- Use `[[Note Name|Display Text]]` when display text differs from note name
- Use `[[Note Name#Heading]]` to link to specific sections
- Use `![[Note Name]]` for transclusion (embedding note content)

### Frontmatter
Every note should have YAML frontmatter:

```yaml
---
title: Note Title
created: YYYY-MM-DD
modified: YYYY-MM-DD
tags:
  - tag-one
  - tag-two
aliases:
  - alternate name
---
```

### Tags
- Format: `#lowercase-with-dashes`
- Common tags: #japanese, #homelab, #docker, #project, #reference, #daily
- Nested tags: `#project/active`, `#japanese/vocabulary`

### Headings
- Use H1 (`#`) only for note title (usually matches filename)
- Use H2 (`##`) for major sections
- Use H3 (`###`) for subsections
- Never skip heading levels

### Code Blocks
- Always specify language for syntax highlighting
- Use `bash` for shell commands
- Use `yaml` for Docker Compose and config files
- Use `powershell` for Windows-specific commands

## Key Areas

### Japanese Learning (02_Areas/Japanese/)
- Vocabulary notes with readings and example sentences
- Grammar patterns and explanations
- Anime/manga notes for immersion learning
- Links to Anki deck content

### Homelab (02_Areas/Homelab/)
- Docker stack documentation
- Network diagrams and configurations
- Service notes and troubleshooting logs
- Related to self-hosted services at lucasdziura.art

### Projects (01_Projects/)
- Each project gets its own folder
- Include: goals, tasks, notes, and archive
- Link to related resources and areas

## File Operations

### Creating Notes
- New captures: `00_Inbox/`
- Daily notes: `daily/YYYY-MM-DD.md`
- Project notes: `01_Projects/[Project Name]/`
- Reference docs: `03_Resources/`

### Moving Notes
- Never delete notes - move to `04_Archive/`
- Maintain link integrity when moving
- Update frontmatter `modified` date

### Searching
Use these commands for efficient search:
```powershell
# Full-text search (PowerShell)
Get-ChildItem -Recurse -Filter "*.md" | Select-String "search term"

# Find by filename
Get-ChildItem -Recurse -Filter "*keyword*"
```

## Templates

### Daily Note Template
Location: `templates/daily.md`

### Project Note Template
Location: `templates/project.md`

### Reference Note Template
Location: `templates/reference.md`

## Preferences

1. **Ask before bulk operations** - Confirm before modifying more than 5 files
2. **Preserve existing content** - Append rather than overwrite when adding to notes
3. **Maintain links** - Update all backlinks when renaming/moving notes
4. **Use templates** - Apply appropriate template when creating new notes
5. **Archive, don't delete** - Move completed/outdated content to 04_Archive

## Integration Points

- **Anki**: Vocabulary notes may reference Anki card IDs (https://anki.lucasdziura.art)
- **Seanime/Jellyfin**: Anime notes link to AniList IDs (https://anime.lucasdziura.art)
- **Manga**: Reading notes for Suwayomi content (https://manga.lucasdziura.art)
- **Daily Briefing**: Weather, schedule data may be referenced

## Common Tasks

### "Process my inbox"
1. Review each note in `00_Inbox/`
2. Add proper frontmatter
3. Determine appropriate location (Projects/Areas/Resources)
4. Move and create relevant links
5. Update any related notes

### "Create a project note for X"
1. Create folder: `01_Projects/X/`
2. Create main note: `01_Projects/X/X.md`
3. Apply project template
4. Link to relevant resources

### "Summarize my week"
1. Read daily notes from past 7 days
2. Extract key accomplishments, learnings, blockers
3. Create summary in current daily note
4. Link to relevant project updates
```

### 9.1 Create Templates

Create `vault/templates/daily.md`:

```markdown
---
title: {{date}}
created: {{date}}
tags:
  - daily
---

# {{date}}

## Morning Review
- [ ] Check calendar
- [ ] Review priorities

## Tasks
- [ ] 

## Notes


## Evening Review
### What went well?

### What could improve?

### Tomorrow's priorities
1. 
2. 
3. 
```

Create `vault/templates/project.md`:

```markdown
---
title: Project Name
created: {{date}}
modified: {{date}}
tags:
  - project
  - project/active
status: active
---

# Project Name

## Overview
Brief description of the project.

## Goals
- [ ] Goal 1
- [ ] Goal 2

## Tasks
- [ ] Task 1
- [ ] Task 2

## Notes

## Resources
- [[Related Note]]

## Log
### {{date}}
- Project created
```

Create `vault/templates/reference.md`:

```markdown
---
title: Reference Title
created: {{date}}
modified: {{date}}
tags:
  - reference
source: 
---

# Reference Title

## Summary

## Key Points

## Details

## Related
- [[Related Note]]
```

---

## 10. Essential Plugins

Install these community plugins in Obsidian:

### Required for Integration
| Plugin | Purpose |
|--------|---------|
| Local REST API | Enables MCP server communication |
| Remotely Save | Cross-device sync via S3 |

### Highly Recommended
| Plugin | Purpose |
|--------|---------|
| Templater | Advanced templates with dynamic dates |
| Dataview | Query vault as database |
| Calendar | Daily note navigation |
| Periodic Notes | Daily/weekly/monthly note management |
| Quick Add | Fast note capture |

### Optional but Useful
| Plugin | Purpose |
|--------|---------|
| Smart Connections | AI-powered semantic search |
| Excalidraw | Diagrams and drawings |
| Kanban | Project task boards |
| Git | Version control backup |

### Plugin Installation

```
Settings > Community Plugins > Browse

Search and install each plugin, then enable.
```

### Templater Configuration

After installing Templater:
1. Settings > Templater
2. Set Template folder location: `templates`
3. Enable "Trigger Templater on new file creation"

---

## 11. Maintenance & Scheduled Jobs

### 11.1 Ofelia Job Schedule

Ofelia handles all scheduled maintenance automatically via Docker labels:

| Time (UTC) | Job | Description |
|------------|-----|-------------|
| 3:00 AM daily | `backup-vault` | Backup vault to `/config/backups/vault-YYYYMMDD.tar.gz` |
| 4:00 AM daily | `cleanup-backups` | Delete backups older than 30 days |
| 4:00 AM Sunday | `restart-obsidian` | Restart Obsidian (clears Electron memory leaks) |

### 11.2 View Job Status

```bash
# Check Ofelia logs for job execution
docker logs obsidian-ofelia

# Follow logs in real-time
docker logs -f obsidian-ofelia
```

### 11.3 Manual Backup

```bash
# Create manual backup
docker exec obsidian sh -c 'tar -czf /config/backups/vault-manual-$(date +%Y%m%d-%H%M%S).tar.gz -C /vault .'

# List backups
docker exec obsidian ls -la /config/backups/
```

### 11.4 Restore from Backup

```bash
# Stop Obsidian
docker compose stop obsidian

# Extract backup (replace with your backup filename)
docker run --rm -v obsidian-docker_vault:/vault -v ./obsidian-config/backups:/backups alpine \
  sh -c 'rm -rf /vault/* && tar -xzf /backups/vault-20260127.tar.gz -C /vault'

# Start Obsidian
docker compose start obsidian
```

### 11.5 Docker Container Updates

```powershell
cd W:\PersonalProjects\self-hosted-stack\obsidian-docker

# Pull latest images
docker compose pull

# Recreate containers with new images
docker compose up -d

# Cleanup old images
docker image prune -f
```

---

## 12. Troubleshooting

### Common Issues

**Obsidian crashes immediately**
- Ensure `shm_size: "1gb"` is set in docker-compose.yml
- Check logs: `docker logs obsidian`

**Can't connect via web browser**
- Verify Tailscale is connected: `docker exec obsidian-tailscale tailscale status`
- Check Caddy logs: `docker logs obsidian-caddy`
- Ensure DNS records point to correct Tailscale IP
- Ensure you're on the Tailscale network

**Sync not working (Remotely Save)**
- Verify R2 credentials and bucket name
- Check "Check Connectivity" in plugin settings
- Ensure bucket has correct permissions

**MCP server not connecting**
- Verify Local REST API plugin is enabled in Obsidian
- Check API key is correct in claude_desktop_config.json
- Restart Claude Desktop after config changes
- Test API manually: `curl http://127.0.0.1:27124/vault/` with appropriate auth header

**Slow performance on large vault**
- Consider using cyanheads MCP server with caching
- Use Claude Code direct filesystem access instead of MCP
- Limit Dataview queries

### Useful Commands

```bash
# View Obsidian logs
docker logs -f obsidian

# View Ofelia job logs
docker logs -f obsidian-ofelia

# Enter container shell
docker exec -it obsidian bash

# Check Tailscale status
docker exec obsidian-tailscale tailscale status

# Restart stack
docker compose restart

# Full rebuild
docker compose down && docker compose up -d
```

### Health Checks

```bash
# Check container status
docker compose ps

# Check resource usage
docker stats obsidian

# Check vault size (from host)
du -sh W:\PersonalProjects\self-hosted-stack\obsidian-docker\vault

# Check backups
docker exec obsidian ls -la /config/backups/
```

---

## Quick Reference

| Component | URL/Path |
|-----------|----------|
| Web UI | `https://obsidian.lucasdziura.art` |
| REST API (remote) | `https://obsidian-api.lucasdziura.art` |
| Local HTTPS | `https://localhost:13443` |
| REST API (local) | `http://localhost:27124` |
| Vault Path (Container) | `/vault` |
| Vault Path (Host) | `W:\PersonalProjects\self-hosted-stack\obsidian-docker\vault` |
| Config Path | `W:\PersonalProjects\self-hosted-stack\obsidian-docker\obsidian-config` |
| Backups | `W:\PersonalProjects\self-hosted-stack\obsidian-docker\obsidian-config\backups` |

---

## Next Steps After Deployment

1. [ ] Create directory structure
2. [ ] Create `.env` and `Caddyfile`
3. [ ] Deploy Docker stack
4. [ ] Get Tailscale IP and update Cloudflare DNS
5. [ ] Access web UI and open vault at `/vault`
6. [ ] Set up Cloudflare R2 bucket
7. [ ] Install and configure Remotely Save plugin
8. [ ] Create CLAUDE.md and templates
9. [ ] Install essential plugins (Local REST API, Templater, etc.)
10. [ ] Configure MCP server for Claude Desktop
11. [ ] Test Claude Code integration with vault
12. [ ] Verify Ofelia backup jobs are running
13. [ ] Sync to additional devices
