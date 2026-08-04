import asyncio
import json

from fastmcp import Client
from fastmcp.client.transports import SSETransport


def serializable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


async def main():
    transport = SSETransport(url="http://127.0.0.1:8000/mcp")
    async with Client(transport) as client:
        tools = await client.list_tools()
        names = [tool.name for tool in tools]
        projects = await client.call_tool(
            "list_memory_projects", {"output_format": "json"}
        )
        directory_results = {}
        search_results = {}
        for project, query in (("mirror", "emotional"), ("life-os", "schedule")):
            listing = await client.call_tool(
                "list_directory",
                {
                    "project": project,
                    "depth": 2,
                    "file_name_glob": "*.md",
                },
            )
            directory_results[project] = serializable(listing.data)
            match = await client.call_tool(
                "search_notes",
                {
                    "project": project,
                    "query": query,
                    "search_type": "text",
                    "page_size": 3,
                    "output_format": "json",
                },
            )
            match_data = serializable(match.data)
            if isinstance(match_data, dict):
                search_results[project] = {
                    "total": match_data.get("total"),
                    "matches": [
                        {
                            "title": item.get("title"),
                            "file_path": item.get("file_path"),
                        }
                        for item in match_data.get("results", [])
                    ],
                }
            else:
                search_results[project] = match_data
        output = {
            "tool_count": len(names),
            "tools": names,
            "projects": [
                item["name"]
                for item in (serializable(projects.data) or {}).get("projects", [])
            ],
            "directories": directory_results,
            "searches": search_results,
        }
        print(json.dumps(output, indent=2, default=str))


asyncio.run(main())
