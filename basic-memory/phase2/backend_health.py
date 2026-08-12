import socket
import sys
from urllib.parse import urlparse


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"
    parsed = urlparse(url)
    if not parsed.hostname:
        raise SystemExit("health URL must include a hostname")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    with socket.create_connection((parsed.hostname, port), timeout=5):
        pass


main()
