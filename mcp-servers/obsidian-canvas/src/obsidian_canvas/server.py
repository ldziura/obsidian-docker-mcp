"""FastMCP server providing Obsidian Canvas tools via the Local REST API."""

from __future__ import annotations

import json
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP

from .api_client import ObsidianAPIClient
from .canvas import (
    CanvasData,
    Edge,
    FileNode,
    GroupNode,
    LinkNode,
    TextNode,
    add_edge_to_canvas,
    add_node_to_canvas,
    remove_edge_from_canvas,
    remove_node_from_canvas,
    update_node_in_canvas,
)

logger = logging.getLogger("obsidian-canvas-mcp")

mcp = FastMCP("obsidian-canvas")


def _get_client() -> ObsidianAPIClient:
    api_key = os.environ.get("OBSIDIAN_API_KEY")
    if not api_key:
        raise ValueError("OBSIDIAN_API_KEY environment variable is required")
    host = os.environ.get("OBSIDIAN_HOST", "127.0.0.1")
    port = int(os.environ.get("OBSIDIAN_PORT", "27124"))
    https = os.environ.get("OBSIDIAN_HTTPS", "false").lower() == "true"
    return ObsidianAPIClient(api_key=api_key, host=host, port=port, https=https)


def _ensure_ext(path: str) -> str:
    if not path.endswith(".canvas"):
        path += ".canvas"
    return path


def _build_node(
    node_type: str,
    x: int,
    y: int,
    width: int,
    height: int,
    color: str | None,
    text: str | None,
    file: str | None,
    subpath: str | None,
    url: str | None,
    label: str | None,
    background: str | None,
    backgroundStyle: str | None,
):
    base = dict(x=x, y=y, width=width, height=height)
    if color is not None:
        base["color"] = color
    match node_type:
        case "text":
            if text is None:
                raise ValueError("'text' is required for text nodes")
            return TextNode(text=text, **base)
        case "file":
            if file is None:
                raise ValueError("'file' is required for file nodes")
            kw = dict(file=file, **base)
            if subpath is not None:
                kw["subpath"] = subpath
            return FileNode(**kw)
        case "link":
            if url is None:
                raise ValueError("'url' is required for link nodes")
            return LinkNode(url=url, **base)
        case "group":
            kw = dict(**base)
            if label is not None:
                kw["label"] = label
            if background is not None:
                kw["background"] = background
            if backgroundStyle is not None:
                kw["backgroundStyle"] = backgroundStyle
            return GroupNode(**kw)
        case _:
            raise ValueError(
                f"Unknown node type '{node_type}'. Use: text, file, link, group"
            )


# --- Tools ---


@mcp.tool()
async def list_canvases() -> str:
    """List all .canvas files in the vault.

    Returns a JSON array of vault-relative paths.
    """
    try:
        client = _get_client()
        files = await client.list_files()
        await client.close()
        canvases = [f for f in files if f.endswith(".canvas")]
        return json.dumps(canvases, indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def create_canvas(
    path: str,
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
) -> str:
    """Create a new .canvas file in the vault.

    Args:
        path: Vault-relative path (e.g. "01_Projects/roadmap.canvas").
              .canvas extension added automatically if missing.
        nodes: Optional initial nodes. Each needs: type, x, y, and type-specific
               fields (text for "text", file for "file", url for "link").
               IDs are auto-generated if not provided.
        edges: Optional initial edges. Each needs: fromNode, toNode.
    """
    try:
        canvas = CanvasData(
            nodes=[_parse_node_dict(n) for n in (nodes or [])],
            edges=[Edge.model_validate(e) for e in (edges or [])],
        )
        client = _get_client()
        await client.put_file(_ensure_ext(path), canvas.to_json())
        await client.close()
        return canvas.to_json()
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def read_canvas(path: str) -> str:
    """Read a .canvas file and return its structured data.

    Args:
        path: Vault-relative path to the .canvas file.

    Returns the canvas JSON with a summary of node/edge counts.
    """
    try:
        client = _get_client()
        raw = await client.get_file(_ensure_ext(path))
        await client.close()
        canvas = CanvasData.from_json(raw)
        type_counts = {}
        for n in canvas.nodes:
            t = n.type
            type_counts[t] = type_counts.get(t, 0) + 1
        type_summary = ", ".join(f"{c} {t}" for t, c in type_counts.items())
        summary = (
            f"Canvas has {len(canvas.nodes)} node(s) ({type_summary}) "
            f"and {len(canvas.edges)} edge(s)."
        )
        return f"{summary}\n\n{canvas.to_json()}"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Canvas file not found: {path}"
        return f"Error: Obsidian API returned {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def add_node(
    path: str,
    type: str,
    x: int,
    y: int,
    width: int = 400,
    height: int = 400,
    color: str | None = None,
    text: str | None = None,
    file: str | None = None,
    subpath: str | None = None,
    url: str | None = None,
    label: str | None = None,
    background: str | None = None,
    backgroundStyle: str | None = None,
) -> str:
    """Add a node to an existing canvas.

    Args:
        path: Vault-relative path to the .canvas file.
        type: Node type - "text", "file", "link", or "group".
        x: X position on canvas.
        y: Y position on canvas.
        width: Node width (default 400).
        height: Node height (default 400).
        color: Hex "#RRGGBB" or preset "1"-"6" (1=red 2=orange 3=yellow 4=green 5=cyan 6=purple).
        text: Markdown content (required for type="text").
        file: Vault path to file (required for type="file").
        subpath: Heading/block link for file nodes (e.g. "#heading").
        url: URL string (required for type="link").
        label: Label for group nodes.
        background: Background image path for group nodes.
        backgroundStyle: "cover", "ratio", or "repeat" for group nodes.

    Returns the created node JSON including its auto-generated ID.
    """
    try:
        node = _build_node(
            type, x, y, width, height, color,
            text, file, subpath, url, label, background, backgroundStyle,
        )
        client = _get_client()
        raw = await client.get_file(_ensure_ext(path))
        canvas = CanvasData.from_json(raw)
        add_node_to_canvas(canvas, node)
        await client.put_file(_ensure_ext(path), canvas.to_json())
        await client.close()
        return node.model_dump_json(exclude_none=True, indent=2)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Canvas file not found: {path}"
        return f"Error: Obsidian API returned {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def update_node(
    path: str,
    node_id: str,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    color: str | None = None,
    text: str | None = None,
    file: str | None = None,
    subpath: str | None = None,
    url: str | None = None,
    label: str | None = None,
    background: str | None = None,
    backgroundStyle: str | None = None,
) -> str:
    """Update properties of an existing node. Only provided fields are changed.

    Args:
        path: Vault-relative path to the .canvas file.
        node_id: ID of the node to update.
        [other args]: Only fields you provide will be updated.
    """
    try:
        updates = {}
        for key, val in [
            ("x", x), ("y", y), ("width", width), ("height", height),
            ("color", color), ("text", text), ("file", file),
            ("subpath", subpath), ("url", url), ("label", label),
            ("background", background), ("backgroundStyle", backgroundStyle),
        ]:
            if val is not None:
                updates[key] = val
        if not updates:
            return "Error: No fields to update provided."
        client = _get_client()
        raw = await client.get_file(_ensure_ext(path))
        canvas = CanvasData.from_json(raw)
        update_node_in_canvas(canvas, node_id, updates)
        await client.put_file(_ensure_ext(path), canvas.to_json())
        await client.close()
        node = next(n for n in canvas.nodes if n.id == node_id)
        return node.model_dump_json(exclude_none=True, indent=2)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Canvas file not found: {path}"
        return f"Error: Obsidian API returned {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def remove_node(path: str, node_id: str) -> str:
    """Remove a node and all its connected edges from a canvas.

    Args:
        path: Vault-relative path to the .canvas file.
        node_id: ID of the node to remove.
    """
    try:
        client = _get_client()
        raw = await client.get_file(_ensure_ext(path))
        canvas = CanvasData.from_json(raw)
        canvas, removed_edges = remove_node_from_canvas(canvas, node_id)
        await client.put_file(_ensure_ext(path), canvas.to_json())
        await client.close()
        msg = f"Removed node '{node_id}'"
        if removed_edges:
            msg += f" and {removed_edges} connected edge(s)"
        return f"{msg} from {path}."
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Canvas file not found: {path}"
        return f"Error: Obsidian API returned {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def add_edge(
    path: str,
    fromNode: str,
    toNode: str,
    fromSide: str | None = None,
    toSide: str | None = None,
    fromEnd: str | None = None,
    toEnd: str | None = None,
    color: str | None = None,
    label: str | None = None,
) -> str:
    """Add an edge (connection) between two nodes on a canvas.

    Args:
        path: Vault-relative path to the .canvas file.
        fromNode: ID of the source node.
        toNode: ID of the target node.
        fromSide: Side of source node: "top", "right", "bottom", "left".
        toSide: Side of target node: "top", "right", "bottom", "left".
        fromEnd: Source endpoint: "none" or "arrow".
        toEnd: Target endpoint: "none" or "arrow".
        color: Edge color (hex or preset "1"-"6").
        label: Text label on the edge.

    Returns the created edge JSON including its auto-generated ID.
    """
    try:
        edge_data: dict = {"fromNode": fromNode, "toNode": toNode}
        for key, val in [
            ("fromSide", fromSide), ("toSide", toSide),
            ("fromEnd", fromEnd), ("toEnd", toEnd),
            ("color", color), ("label", label),
        ]:
            if val is not None:
                edge_data[key] = val
        edge = Edge.model_validate(edge_data)
        client = _get_client()
        raw = await client.get_file(_ensure_ext(path))
        canvas = CanvasData.from_json(raw)
        add_edge_to_canvas(canvas, edge)
        await client.put_file(_ensure_ext(path), canvas.to_json())
        await client.close()
        return edge.model_dump_json(exclude_none=True, indent=2)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Canvas file not found: {path}"
        return f"Error: Obsidian API returned {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def remove_edge(path: str, edge_id: str) -> str:
    """Remove an edge from a canvas.

    Args:
        path: Vault-relative path to the .canvas file.
        edge_id: ID of the edge to remove.
    """
    try:
        client = _get_client()
        raw = await client.get_file(_ensure_ext(path))
        canvas = CanvasData.from_json(raw)
        remove_edge_from_canvas(canvas, edge_id)
        await client.put_file(_ensure_ext(path), canvas.to_json())
        await client.close()
        return f"Removed edge '{edge_id}' from {path}."
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Canvas file not found: {path}"
        return f"Error: Obsidian API returned {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def _parse_node_dict(data: dict):
    """Parse a raw dict into the correct node model."""
    from .canvas import _parse_node
    return _parse_node(data)


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await mcp._mcp_server.run(
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),
        )
