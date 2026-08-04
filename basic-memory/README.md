# Basic Memory deployment

Version-controlled source and deployment configuration for the self-hosted Basic Memory MCP service.

This directory intentionally excludes credentials, OAuth state, indexes, logs, Git checkouts, and generated runtime data.

## Components

| Repository file | Deployed location | Purpose |
|---|---|---|
| `gateway.py` | `/srv/basic-memory/gateway.py` | Authenticated MCP adapter and constrained Basic Memory tool surface |
| `Dockerfile.gateway` | Build context | Custom gateway container image |
| `docker-compose.yml` | `/srv/basic-memory/docker-compose.yml` | Basic Memory and gateway services |
| `config.json` | `/srv/basic-memory/config/config.json` | Basic Memory project mapping and search configuration |
| `basic-memory-git-sync` | `/usr/local/sbin/basic-memory-git-sync` | Periodic Git synchronization |
| `basic-memory-git-sync.service` | `/etc/systemd/system/basic-memory-git-sync.service` | Hardened one-shot sync unit |
| `basic-memory-git-sync.timer` | `/etc/systemd/system/basic-memory-git-sync.timer` | Five-minute sync schedule |
| `Caddyfile` | `/home/ubuntu/caddy/Caddyfile` | HTTPS reverse proxy |
| `validate_mcp.py` | Operator workstation or host | Non-mutating backend validation |
| `gateway.env.example` | Template only | Required gateway environment variable names |

## Secret handling

Create `/srv/basic-memory/secrets/gateway.env` directly on the host from `gateway.env.example`. Never commit its values. Keep it owned by `root:root` with mode `0600`.

The following are runtime state and must also remain untracked:

- OAuth token storage
- Basic Memory databases and indexes
- checked-out knowledge repositories
- Git or SSH credentials
- TLS private keys
- synchronization status and logs

## Current deployed baseline

- Basic Memory image: `ghcr.io/basicmachines-co/basic-memory:0.21.5`
- Gateway image tag: `basic-memory-gateway:0.21.5-2`
- FastMCP: `3.3.1`
- Public transport: authenticated HTTPS through Caddy
- Projects: `mirror` and `life-os`
- Search exposed by the gateway: keyword-only
- Git synchronization: systemd timer every five minutes

These files capture the existing deployment. Architectural hardening should be proposed through reviewed changes rather than editing the live host first.

## Validation

Before deployment:

```bash
python -m py_compile gateway.py validate_mcp.py
docker compose config --quiet
```

After deployment, run `validate_mcp.py` inside an authorized maintenance environment and inspect service health without printing secrets.
