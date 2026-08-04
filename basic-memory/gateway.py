import json
import logging
import os
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from cryptography.fernet import Fernet
from fastmcp import Client, FastMCP
from fastmcp.client.transports import SSETransport
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AuthContext
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.middleware import AuthMiddleware
from key_value.aio.stores.disk import DiskStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from mcp.types import ToolAnnotations


Project = Literal["mirror", "life-os"]
EditOperation = Literal[
    "append",
    "prepend",
    "find_replace",
    "replace_section",
    "insert_before_section",
    "insert_after_section",
]

BACKEND_URL = os.environ.get(
    "BASIC_MEMORY_BACKEND_URL", "http://basic-memory:8000/mcp"
)
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")
EXPECTED_GITHUB_USER_ID = os.environ["EXPECTED_GITHUB_USER_ID"]
OAUTH_STORAGE_DIR = os.environ.get("OAUTH_STORAGE_DIR", "/var/lib/fastmcp/oauth")
GIT_SYNC_STATUS_FILE = Path(
    os.environ.get(
        "GIT_SYNC_STATUS_FILE", "/var/lib/basic-memory-host/git-sync-status.json"
    )
)
LOGGER = logging.getLogger("basic_memory_gateway")


def require_owner(ctx: AuthContext) -> bool:
    if ctx.token is None:
        raise AuthorizationError("Authentication is required")
    claims = ctx.token.claims or {}
    actual_id = claims.get("sub")
    if str(actual_id) != EXPECTED_GITHUB_USER_ID:
        LOGGER.warning("Owner authorization failed for an MCP component")
        raise AuthorizationError("This MCP server is restricted to its owner")
    return True


encrypted_storage = FernetEncryptionWrapper(
    key_value=DiskStore(directory=OAUTH_STORAGE_DIR),
    fernet=Fernet(os.environ["STORAGE_ENCRYPTION_KEY"].encode()),
)

auth = GitHubProvider(
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    base_url=PUBLIC_BASE_URL,
    required_scopes=["read:user"],
    jwt_signing_key=os.environ["JWT_SIGNING_KEY"],
    client_storage=encrypted_storage,
)

mcp = FastMCP(
    "Private Basic Memory",
    auth=auth,
    middleware=[AuthMiddleware(auth=require_owner)],
    instructions=(
        "Private knowledge service with two isolated projects: mirror and life-os. "
        "Always choose the project explicitly. Destructive operations are disabled."
    ),
)

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE_SAFE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
OAUTH_META = {
    "securitySchemes": [{"type": "oauth2", "scopes": ["read:user"]}],
    "openai/visibility": "public",
}


def _safe_relative_path(value: str, field: str) -> str:
    value = value.strip()
    path = PurePosixPath(value or ".")
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must stay within the selected project")
    return "" if value in ("", ".") else value


def _safe_identifier(project: Project, identifier: str) -> str:
    identifier = identifier.strip()
    if not identifier:
        raise ValueError("identifier cannot be empty")
    if identifier.startswith("memory://"):
        remainder = identifier.removeprefix("memory://").lstrip("/")
        prefix = remainder.split("/", 1)[0]
        if prefix in ("mirror", "life-os") and prefix != project:
            raise ValueError("memory URL belongs to a different project")
    elif identifier.startswith("/") or ".." in PurePosixPath(identifier).parts:
        raise ValueError("identifier must stay within the selected project")
    return identifier


def _payload(result: Any) -> dict[str, Any]:
    if result.structured_content is not None:
        return result.structured_content
    if result.data is not None:
        return json.loads(json.dumps(result.data, default=str))
    content = []
    for block in result.content:
        if hasattr(block, "model_dump"):
            content.append(block.model_dump(mode="json"))
        elif hasattr(block, "text"):
            content.append({"type": "text", "text": block.text})
        else:
            content.append({"type": "unknown", "value": str(block)})
    return {"content": content}


async def _call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    transport = SSETransport(url=BACKEND_URL)
    async with Client(transport) as client:
        result = await client.call_tool(tool, arguments)
        return _payload(result)


@mcp.tool(annotations=READ_ONLY, meta=OAUTH_META, output_schema=None)
async def list_memory_projects() -> dict[str, Any]:
    """List the two available private knowledge projects."""
    return await _call("list_memory_projects", {"output_format": "json"})


@mcp.tool(annotations=READ_ONLY, meta=OAUTH_META, output_schema=None)
async def git_sync_status() -> dict[str, Any]:
    """Report the last conflict-safe Git synchronization result."""
    if not GIT_SYNC_STATUS_FILE.exists():
        return {"status": "not-run"}
    return json.loads(GIT_SYNC_STATUS_FILE.read_text())


@mcp.tool(annotations=READ_ONLY, meta=OAUTH_META, output_schema=None)
async def search_notes(
    project: Project,
    query: str,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    """Run keyword-only search in exactly one selected project."""
    if not query.strip():
        raise ValueError("query cannot be empty")
    if page < 1 or not 1 <= page_size <= 50:
        raise ValueError("page must be >= 1 and page_size must be between 1 and 50")
    return await _call(
        "search_notes",
        {
            "project": project,
            "query": query,
            "page": page,
            "page_size": page_size,
            "search_type": "text",
            "search_all_projects": False,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=READ_ONLY, meta=OAUTH_META, output_schema=None)
async def read_note(
    project: Project,
    identifier: str,
    include_frontmatter: bool = False,
) -> dict[str, Any]:
    """Read one note from the selected project."""
    return await _call(
        "read_note",
        {
            "project": project,
            "identifier": _safe_identifier(project, identifier),
            "include_frontmatter": include_frontmatter,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=READ_ONLY, meta=OAUTH_META, output_schema=None)
async def list_notes(
    project: Project,
    directory: str = "",
    depth: int = 2,
    pattern: str = "*.md",
) -> dict[str, Any]:
    """List notes in a project directory without leaving the selected project."""
    if not 1 <= depth <= 5:
        raise ValueError("depth must be between 1 and 5")
    return await _call(
        "list_directory",
        {
            "project": project,
            "dir_name": _safe_relative_path(directory, "directory"),
            "depth": depth,
            "file_name_glob": pattern,
        },
    )


@mcp.tool(annotations=READ_ONLY, meta=OAUTH_META, output_schema=None)
async def recent_activity(
    project: Project,
    timeframe: str = "30d",
    page_size: int = 10,
) -> dict[str, Any]:
    """Return recent indexed activity from exactly one project."""
    if not 1 <= page_size <= 50:
        raise ValueError("page_size must be between 1 and 50")
    return await _call(
        "recent_activity",
        {
            "project": project,
            "timeframe": timeframe,
            "page_size": page_size,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=WRITE_SAFE, meta=OAUTH_META, output_schema=None)
async def write_note(
    project: Project,
    title: str,
    content: str,
    directory: str,
    tags: list[str] | None = None,
    note_type: str = "note",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new note. Existing notes are never overwritten by this tool."""
    if not title.strip() or not content.strip():
        raise ValueError("title and content cannot be empty")
    return await _call(
        "write_note",
        {
            "project": project,
            "title": title,
            "content": content,
            "directory": _safe_relative_path(directory, "directory"),
            "tags": tags or [],
            "note_type": note_type,
            "metadata": metadata or {},
            "overwrite": False,
            "output_format": "json",
        },
    )


@mcp.tool(annotations=WRITE_SAFE, meta=OAUTH_META, output_schema=None)
async def edit_note(
    project: Project,
    identifier: str,
    operation: EditOperation,
    content: str,
    section: str | None = None,
    find_text: str | None = None,
    expected_replacements: int = 1,
) -> dict[str, Any]:
    """Edit an existing note incrementally; whole-note deletion is unavailable."""
    if not content:
        raise ValueError("content cannot be empty")
    arguments: dict[str, Any] = {
        "project": project,
        "identifier": _safe_identifier(project, identifier),
        "operation": operation,
        "content": content,
        "expected_replacements": expected_replacements,
        "output_format": "json",
    }
    if section is not None:
        arguments["section"] = section
    if find_text is not None:
        arguments["find_text"] = find_text
    return await _call("edit_note", arguments)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)
