import os
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.server.middleware import AuthMiddleware

from gateway_common import (
    DESTRUCTIVE_ANNOTATIONS,
    OAUTH_META,
    READ_ONLY_ANNOTATIONS,
    WRITE_ANNOTATIONS,
    build_auth,
    call_backend,
    chatgpt_fetch_result,
    chatgpt_search_result,
    require_owner,
    safe_identifier,
    safe_memory_url,
    safe_relative_path,
)


Project = Literal["mirror", "phase2-verification"]
EditOperation = Literal[
    "append",
    "prepend",
    "find_replace",
    "replace_section",
    "insert_before_section",
    "insert_after_section",
]

BACKEND_URL = os.environ.get("BASIC_MEMORY_BACKEND_URL", "http://general-backend:8000/mcp")
ALLOWED_BACKEND_TOOLS = frozenset(
    {
        "search_notes",
        "read_note",
        "list_directory",
        "recent_activity",
        "build_context",
        "write_note",
        "edit_note",
        "move_note",
        "delete_note",
    }
)

auth = build_auth()
mcp = FastMCP(
    "General Basic Memory",
    auth=auth,
    middleware=[AuthMiddleware(auth=require_owner)],
    instructions=(
        "Authenticated read/write Basic Memory access for explicitly authorized non-Life-OS projects. "
        "The Life OS project is unavailable on this endpoint."
    ),
)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def search(project: Project, query: str) -> list[dict[str, str]]:
    """Search an authorized non-Life-OS project."""
    if not query.strip():
        raise ValueError("query cannot be empty")
    payload = await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "search_notes",
        {
            "project": project,
            "query": query,
            "page": 1,
            "page_size": 10,
            "search_type": "text",
            "search_all_projects": False,
            "output_format": "json",
        },
    )
    return chatgpt_search_result(payload, query)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def fetch(project: Project, id: str) -> list[dict[str, str]]:
    """Fetch a complete note from an authorized non-Life-OS project."""
    identifier = safe_identifier(project, id)
    payload = await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "read_note",
        {
            "project": project,
            "identifier": identifier,
            "include_frontmatter": True,
            "output_format": "text",
        },
    )
    return chatgpt_fetch_result(payload, identifier)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def read_note(project: Project, identifier: str, include_frontmatter: bool = True) -> Any:
    """Read a note from an authorized non-Life-OS project."""
    return await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "read_note",
        {
            "project": project,
            "identifier": safe_identifier(project, identifier),
            "include_frontmatter": include_frontmatter,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def list_notes(
    project: Project,
    directory: str = "",
    depth: int = 2,
    pattern: str = "*.md",
) -> Any:
    """List notes in an authorized non-Life-OS project."""
    if not 1 <= depth <= 5:
        raise ValueError("depth must be between 1 and 5")
    return await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "list_directory",
        {
            "project": project,
            "dir_name": safe_relative_path(directory, "directory"),
            "depth": depth,
            "file_name_glob": pattern,
        },
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def recent_activity(project: Project, timeframe: str = "30d", page_size: int = 10) -> Any:
    """Return recent activity from an authorized non-Life-OS project."""
    if not 1 <= page_size <= 50:
        raise ValueError("page_size must be between 1 and 50")
    return await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "recent_activity",
        {
            "project": project,
            "timeframe": timeframe,
            "page_size": page_size,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def build_context(
    project: Project,
    url: str,
    depth: int = 1,
    timeframe: str = "7d",
    max_related: int = 10,
) -> Any:
    """Build related-note context inside an authorized non-Life-OS project."""
    if not 1 <= depth <= 3:
        raise ValueError("depth must be between 1 and 3")
    return await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "build_context",
        {
            "project": project,
            "url": safe_memory_url(project, url),
            "depth": depth,
            "timeframe": timeframe,
            "max_related": max_related,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def write_note(
    project: Project,
    title: str,
    content: str,
    directory: str,
    tags: list[str] | None = None,
    note_type: str = "note",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Create a note without overwriting an existing note."""
    if not title.strip() or not content.strip():
        raise ValueError("title and content cannot be empty")
    return await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "write_note",
        {
            "project": project,
            "title": title,
            "content": content,
            "directory": safe_relative_path(directory, "directory"),
            "tags": tags or [],
            "note_type": note_type,
            "metadata": metadata or {},
            "overwrite": False,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=WRITE_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def edit_note(
    project: Project,
    identifier: str,
    operation: EditOperation,
    content: str,
    section: str | None = None,
    find_text: str | None = None,
    expected_replacements: int | None = None,
) -> Any:
    """Edit an existing note incrementally."""
    if not content:
        raise ValueError("content cannot be empty")
    arguments: dict[str, Any] = {
        "project": project,
        "identifier": safe_identifier(project, identifier),
        "operation": operation,
        "content": content,
        "output_format": "json",
    }
    if section is not None:
        arguments["section"] = section
    if find_text is not None:
        arguments["find_text"] = find_text
    if expected_replacements is not None:
        arguments["expected_replacements"] = expected_replacements
    return await call_backend(BACKEND_URL, ALLOWED_BACKEND_TOOLS, "edit_note", arguments)


@mcp.tool(annotations=WRITE_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def move_note(
    project: Project,
    identifier: str,
    destination_path: str = "",
    destination_folder: str | None = None,
) -> Any:
    """Move or rename one note inside an authorized project."""
    if bool(destination_path) == bool(destination_folder):
        raise ValueError("provide exactly one of destination_path or destination_folder")
    arguments: dict[str, Any] = {
        "project": project,
        "identifier": safe_identifier(project, identifier),
        "is_directory": False,
        "output_format": "json",
    }
    if destination_path:
        arguments["destination_path"] = safe_relative_path(destination_path, "destination_path")
    if destination_folder:
        arguments["destination_folder"] = safe_relative_path(destination_folder, "destination_folder")
    return await call_backend(BACKEND_URL, ALLOWED_BACKEND_TOOLS, "move_note", arguments)


@mcp.tool(annotations=DESTRUCTIVE_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def delete_note(project: Project, identifier: str) -> Any:
    """Permanently delete one note from an authorized non-Life-OS project."""
    return await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "delete_note",
        {
            "project": project,
            "identifier": safe_identifier(project, identifier),
            "is_directory": False,
            "output_format": "json",
        },
    )


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)
