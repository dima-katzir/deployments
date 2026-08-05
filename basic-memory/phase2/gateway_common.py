import json
import logging
import os
from pathlib import PurePosixPath
from typing import Any

from cryptography.fernet import Fernet
from fastmcp import Client
from fastmcp.client.transports import SSETransport
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AuthContext
from fastmcp.server.auth.providers.github import GitHubProvider
from key_value.aio.stores.disk import DiskStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper


LOGGER = logging.getLogger("basic_memory_phase2_gateway")

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}
DESTRUCTIVE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}
OAUTH_META = {
    "securitySchemes": [{"type": "oauth2", "scopes": ["read:user"]}],
    "openai/visibility": "public",
}


def require_owner(ctx: AuthContext) -> bool:
    if ctx.token is None:
        raise AuthorizationError("Authentication is required")
    claims = ctx.token.claims or {}
    if str(claims.get("sub")) != os.environ["EXPECTED_GITHUB_USER_ID"]:
        LOGGER.warning("Owner authorization failed for an MCP component")
        raise AuthorizationError("This MCP server is restricted to its owner")
    return True


def build_auth() -> GitHubProvider:
    storage = FernetEncryptionWrapper(
        key_value=DiskStore(directory=os.environ["OAUTH_STORAGE_DIR"]),
        fernet=Fernet(os.environ["STORAGE_ENCRYPTION_KEY"].encode()),
    )
    return GitHubProvider(
        client_id=os.environ["GITHUB_CLIENT_ID"],
        client_secret=os.environ["GITHUB_CLIENT_SECRET"],
        base_url=os.environ["PUBLIC_BASE_URL"].rstrip("/"),
        required_scopes=["read:user"],
        jwt_signing_key=os.environ["JWT_SIGNING_KEY"],
        client_storage=storage,
    )


def safe_relative_path(value: str, field: str) -> str:
    cleaned = value.strip()
    path = PurePosixPath(cleaned or ".")
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must stay within the selected project")
    return "" if cleaned in ("", ".") else cleaned


def safe_identifier(project: str, identifier: str) -> str:
    cleaned = identifier.strip()
    if not cleaned:
        raise ValueError("identifier cannot be empty")
    if cleaned.startswith("memory://"):
        remainder = cleaned.removeprefix("memory://").lstrip("/")
        prefix = remainder.split("/", 1)[0]
        if prefix and prefix != project:
            raise ValueError("memory URL belongs to a different project")
    elif cleaned.startswith("/") or ".." in PurePosixPath(cleaned).parts:
        raise ValueError("identifier must stay within the selected project")
    return cleaned


def safe_memory_url(project: str, value: str) -> str:
    cleaned = safe_identifier(project, value)
    if cleaned.startswith("memory://"):
        return cleaned
    return f"memory://{project}/{cleaned.lstrip('/')}"


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


async def call_backend(
    backend_url: str,
    allowed_tools: frozenset[str],
    tool: str,
    arguments: dict[str, Any],
) -> Any:
    if tool not in allowed_tools:
        raise AuthorizationError("Backend tool is not allowed by this endpoint")

    async with Client(SSETransport(url=backend_url)) as client:
        result = await client.call_tool(tool, arguments)

    if result.structured_content is not None:
        return _json_safe(result.structured_content)
    if result.data is not None:
        return _json_safe(result.data)
    if len(result.content) == 1 and hasattr(result.content[0], "text"):
        text = result.content[0].text
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text
    return _json_safe(
        [block.model_dump(mode="json") if hasattr(block, "model_dump") else str(block) for block in result.content]
    )


def chatgpt_search_result(payload: Any, query: str) -> list[dict[str, str]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        raw_results = payload["results"]
    elif isinstance(payload, list):
        raw_results = payload
    else:
        raw_results = []

    results: list[dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        permalink = item.get("permalink") or item.get("id") or ""
        title = item.get("title") or "Untitled"
        results.append({"id": permalink, "title": title, "url": permalink})

    body = {"results": results, "total_count": len(results), "query": query}
    return [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}]


def chatgpt_fetch_result(payload: Any, identifier: str) -> list[dict[str, str]]:
    if isinstance(payload, dict):
        content = payload.get("content") or payload.get("text") or json.dumps(payload, ensure_ascii=False)
        title = payload.get("title")
    else:
        content = str(payload)
        title = None

    if not title:
        title = identifier.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title()
    body = {
        "id": identifier,
        "title": title or "Untitled Document",
        "text": content,
        "url": identifier,
        "metadata": {"format": "markdown"},
    }
    return [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}]
