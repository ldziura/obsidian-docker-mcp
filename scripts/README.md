# Obsidian Scripts

Scripts for configuring and maintaining the Obsidian Docker stack.

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
# Basic setup (will prompt for API key, configures both Claude Code and Desktop)
.\setup-obsidian-mcp.ps1

# With API key and save to environment variable
.\setup-obsidian-mcp.ps1 -ApiKey "your_api_key"

# Skip Claude Desktop configuration
.\setup-obsidian-mcp.ps1 -ApiKey "your_api_key" -SkipClaudeDesktop
```

### Linux/macOS (Bash)

```bash
# Make executable
chmod +x setup-obsidian-mcp.sh

# Basic setup (will prompt for API key, configures both Claude Code and Desktop)
./setup-obsidian-mcp.sh

# With API key and save to shell rc file
./setup-obsidian-mcp.sh --api-key "your_api_key" --set-env

# Skip Claude Desktop configuration
./setup-obsidian-mcp.sh --api-key "your_api_key" --skip-claude-desktop
```

## Manual Configuration

If you prefer manual setup, add this to your configuration files:

### Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["--from", "mcp-obsidian==0.2.1", "mcp-obsidian"],
      "env": {
        "OBSIDIAN_API_KEY": "${OBSIDIAN_API_KEY}",
        "OBSIDIAN_HOST": "obsidian-api.lucasdziura.art",
        "OBSIDIAN_PORT": "443",
        "OBSIDIAN_HTTPS": "true"
      }
    },
    "obsidian-canvas": {
      "command": "uv",
      "args": ["--directory", "/path/to/obsidian-docker/mcp-servers/obsidian-canvas", "run", "obsidian-canvas-mcp"],
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

> **Note:** For `obsidian-canvas`, replace `/path/to/obsidian-docker` with the absolute path to your repo clone. Run `uv sync` inside `mcp-servers/obsidian-canvas/` first to install dependencies.

### Claude Desktop

**Windows (standard):** `%APPDATA%\Claude\claude_desktop_config.json`
**Windows (Store):** `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
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
3. Look for both `obsidian` and `obsidian-canvas` in the connected servers list
4. Test notes: "List files in my Obsidian vault"
5. Test canvas: "List all canvas files in my vault"

## Available MCP Tools

Once connected, Claude has access to two MCP servers:

**Obsidian Notes** (`mcp-obsidian` via PyPI):

| Tool | Description |
|------|-------------|
| `list_files_in_vault` | List all files in the vault |
| `list_files_in_dir` | List files in a specific directory |
| `get_file_contents` | Read a note's content |
| `simple_search` | Search vault by text |
| `append_content` | Add content to end of a note |
| `patch_content` | Insert content at specific location |
| `delete_file` | Delete a note |

**Obsidian Canvas** (`obsidian-canvas-mcp` local package):

| Tool | Description |
|------|-------------|
| `list_canvases` | List all `.canvas` files in the vault |
| `create_canvas` | Create a new canvas file |
| `read_canvas` | Read canvas nodes and edges |
| `add_node` | Add a node (text, file, link, group) |
| `update_node` | Update a node's properties |
| `remove_node` | Remove a node and its connected edges |
| `add_edge` | Connect two nodes |
| `remove_edge` | Remove a connection |

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
  OBSIDIAN_API_KEY="your_key" OBSIDIAN_HOST="obsidian-api.lucasdziura.art" OBSIDIAN_PORT="443" OBSIDIAN_HTTPS="true" uvx --from "mcp-obsidian==0.2.1" mcp-obsidian
  ```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Your Machine                                  │
│  ┌─────────────────┐  stdio  ┌─────────────────────────────────────┐ │
│  │                  │◄───────►│  mcp-obsidian (notes, search)      │ │
│  │   Claude Code    │         └──────────────────┬──────────────────┘ │
│  │                  │  stdio  ┌──────────────────┼──────────────────┐ │
│  │                  │◄───────►│  obsidian-canvas-mcp (canvas ops)  │ │
│  └─────────────────┘         └──────────────────┬──────────────────┘ │
└──────────────────────────────────────────────────┼────────────────────┘
                                                   │ HTTPS/Tailscale
                                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Docker Host                                    │
│  obsidian-api.lucasdziura.art → Caddy → Obsidian REST API            │
└──────────────────────────────────────────────────────────────────────┘
```

Both MCP servers run locally and connect to the same remote Obsidian REST API over Tailscale's encrypted network. `mcp-obsidian` handles notes and search; `obsidian-canvas-mcp` handles canvas file operations.

---

## dedup-transcript-images.py

Deduplicates profile images in meeting transcripts converted from `.docx` by the Dockxer Obsidian plugin. Dockxer stores every speaker profile picture as a separate file, even when the same few speakers alternate throughout. This script identifies duplicates by SHA-256 hash, keeps one copy of each unique image, rewrites the markdown references, and deletes the originals.

### Usage

```bash
# Preview what would change (recommended first run)
python scripts/dedup-transcript-images.py "vault/path/to/transcript.md" --dry-run

# Run for real
python scripts/dedup-transcript-images.py "vault/path/to/transcript.md"

# Custom avatar directory
python scripts/dedup-transcript-images.py "vault/path/to/transcript.md" --avatar-dir "assets/my-avatars"

# Verbose output
python scripts/dedup-transcript-images.py "vault/path/to/transcript.md" -v
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--avatar-dir DIR` | `assets/transcript-avatars` | Vault-relative output directory for unique images |
| `--vault-root DIR` | auto-detected | Override vault root (looks for `.obsidian/`) |
| `--resize PX` | `40` | Resize images by setting alt text to this pixel width |
| `--no-resize` | off | Skip image resizing (only deduplicate) |
| `--dry-run` | off | Show what would change without modifying files |
| `-v, --verbose` | off | Detailed progress output |

### How It Works

1. Parses all `![...](<path>)` image references from the markdown file
2. Hashes each referenced image with SHA-256 to identify duplicates
3. Copies one representative per unique hash to the shared avatar directory
4. Rewrites all markdown references to point to the deduplicated copies
5. Sets image alt text to a pixel width (e.g., `![40]`) for inline sizing
6. Deletes the original duplicate files

### Requirements

- Python 3.11+ (stdlib only, no external dependencies)
- Vault must contain a `.obsidian/` directory (for auto-detection)

---

## resize-transcript-images.py

Resizes images in Obsidian markdown files by setting the alt text to a pixel width. Obsidian renders `![40](<path.png>)` as a 40px-wide image. Useful for making large profile pictures from Dockxer transcripts display inline at a readable size.

### Usage

```bash
# Preview changes
python scripts/resize-transcript-images.py "vault/path/to/transcript.md" --dry-run

# Resize to 40px (default)
python scripts/resize-transcript-images.py "vault/path/to/transcript.md"

# Custom size
python scripts/resize-transcript-images.py "vault/path/to/transcript.md" --size 60
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--size PX` | `40` | Image width in pixels |
| `--dry-run` | off | Show what would change without modifying files |

### Notes

- Idempotent: re-running skips images already at the target size
- Also called automatically by `dedup-transcript-images.py` (use `--no-resize` to skip)
- Python 3.11+, stdlib only

---

## chunk-transcript.py

Splits large Dockxer meeting transcripts into overlapping chunks for parallel AI agent summarization. Uses a sliding window with speaker-turn boundary snapping so chunks never cut mid-utterance. Each chunk includes a metadata header with line range, time range, turn count, and overlap info.

### Usage

```bash
# Preview chunk plan
python scripts/chunk-transcript.py "vault/path/to/transcript.md" --dry-run

# Chunk with defaults (500 lines, 100-line overlap)
python scripts/chunk-transcript.py "vault/path/to/transcript.md"

# Custom chunk size and overlap
python scripts/chunk-transcript.py "vault/path/to/transcript.md" --chunk-size 300 --overlap 60

# Verbose output with turn boundary details
python scripts/chunk-transcript.py "vault/path/to/transcript.md" -v
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--chunk-size LINES` | `500` | Target chunk size in lines |
| `--overlap LINES` | `100` | Number of overlapping lines between adjacent chunks |
| `--output-dir DIR` | `<name>_chunks/` | Output directory (default: sibling folder next to source) |
| `--dry-run` | off | Show chunk plan without writing files |
| `-v, --verbose` | off | Show detailed output including turn boundaries |

### How It Works

1. Parses speaker turn boundaries (avatar + speaker name + timestamp lines)
2. Computes sliding window positions with `stride = chunk_size - overlap`
3. Snaps window start/end to the nearest speaker turn boundary (no mid-utterance cuts)
4. Merges tiny remainders into the previous chunk
5. Writes chunk files with metadata headers to the output directory
6. Cleans up stale chunk files from previous runs

### Notes

- Chunk boundaries snap to speaker turns, so actual sizes vary slightly (~10%) from the target
- The overlap region contains ~20% shared context by default, giving agents continuity across chunks
- If no speaker turns are detected, falls back to naive line-based chunking
- Python 3.11+, stdlib only
