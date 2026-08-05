import asyncio
import sys

from fastmcp import Client
from fastmcp.client.transports import SSETransport


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"
    required = {"search_notes", "read_note"}
    async with Client(SSETransport(url=url)) as client:
        names = {tool.name for tool in await client.list_tools()}
    missing = required - names
    if missing:
        raise SystemExit(f"missing required backend tools: {sorted(missing)}")


asyncio.run(main())
