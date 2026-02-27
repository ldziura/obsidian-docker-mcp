"""Async HTTP client for the Obsidian Local REST API."""

from __future__ import annotations

import httpx


class ObsidianAPIClient:
    """Thin async client wrapping Obsidian's vault file endpoints."""

    def __init__(
        self,
        api_key: str,
        host: str = "127.0.0.1",
        port: int = 27124,
        https: bool = False,
    ):
        protocol = "https" if https else "http"
        self.base_url = f"{protocol}://{host}:{port}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            verify=False,
            timeout=30.0,
        )

    async def get_file(self, path: str) -> str:
        resp = await self._client.get(
            f"/vault/{path}",
            headers={"Accept": "*/*"},
        )
        resp.raise_for_status()
        return resp.text

    async def put_file(self, path: str, content: str) -> None:
        resp = await self._client.put(
            f"/vault/{path}",
            content=content.encode("utf-8"),
            headers={"Content-Type": "application/vnd.olrapi.note+json"},
        )
        resp.raise_for_status()

    async def delete_file(self, path: str) -> None:
        resp = await self._client.delete(f"/vault/{path}")
        resp.raise_for_status()

    async def list_files(self) -> list[str]:
        resp = await self._client.get("/vault/")
        resp.raise_for_status()
        data = resp.json()
        return data.get("files", [])

    async def close(self) -> None:
        await self._client.aclose()
