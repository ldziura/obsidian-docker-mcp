"""Obsidian Canvas MCP Server."""

import asyncio

from .server import main as _main


def main():
    asyncio.run(_main())
