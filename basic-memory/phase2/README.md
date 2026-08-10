# Basic Memory Phase 2 — parallel hardened endpoints

This directory defines the parallel Phase 2 deployment from
`MCP_Project_Target_Architecture.md`. It does not replace the legacy deployment,
implement the Phase 3 Git deployment pipeline, or connect/cut over ChatGPT.

## Pinned inputs

- Basic Memory: `0.22.1`
- Image digest: `sha256:0da35f465fed7b58b6c2e31e7c0dbcbc728760a1b6a71857cfe3ced847c727a1`
- FastMCP: inherited from Basic Memory and pinned upstream at `3.3.1`
- Life OS accepted content SHA: supplied to `materialize_life_os.sh` during deployment

## Isolation model

| Endpoint | Backend projects | Public tools | Data access |
|---|---|---|---|
| `dktzr-life-os.duckdns.org` | `life-os` only | `search`, `fetch` | Life checkout mounted read-only |
| `dktzr-memory.duckdns.org` | `mirror`, disposable `phase2-verification` | Read/search/context and note lifecycle | No Life OS path or network access |

The two backends have separate configuration databases, indexes, Docker
networks, gateways, OAuth stores, OAuth applications, encryption keys, and JWT
signing keys. Neither backend publishes a host port. The public gateways are
bound to loopback for Caddy.

Each backend mounts its committed project registry over
`/home/appuser/.basic-memory/config.json` read-only. This prevents Basic Memory
from silently generating a default `main` project and makes the project
allowlist part of the reviewed deployment source.

Only the Life backend enables semantic embeddings. This is deliberate: Phase 2
requires hybrid semantic retrieval for Life OS, while the host has approximately
1 GiB RAM and must keep the legacy stack available during the parallel stage.

## Filesystem boundary

The deployment materializes the release from an exact accepted Git commit, not
from any working tree:

```bash
sudo ./materialize_life_os.sh \
  /srv/basic-memory/repos/life-os-kb \
  ACCEPTED_SHA \
  /srv/basic-memory-phase2/releases/life-os
```

The resulting `current/` directory is owned by a dedicated release identity,
has no runtime group write bit, and is mounted `ro`. Basic Memory stores its
SQLite index and FastEmbed model in the separate writable state volume.
`ensure_frontmatter_on_sync` is explicitly disabled.

## OAuth setup

Create two separate GitHub OAuth applications:

| Endpoint | Homepage URL | Authorization callback URL |
|---|---|---|
| Life OS | `https://dktzr-life-os.duckdns.org` | `https://dktzr-life-os.duckdns.org/auth/callback` |
| General | `https://dktzr-memory.duckdns.org` | `https://dktzr-memory.duckdns.org/auth/callback` |

Create `life.env` and `general.env` directly under
`/srv/basic-memory-phase2/secrets/`, owned by `root:root` with mode `0600`.
Never paste their values into chat, commit them, or print them in logs.

## Validation order

1. Verify the legacy endpoint before changes.
2. Materialize and checksum the exact ten-file accepted Life OS release.
3. Build the images from the committed source.
4. Start the two backends privately and run the validator.
5. Prove vector and hybrid search and recompute the Life manifest.
6. Start gateways only after distinct OAuth credentials are installed.
7. Add and validate the Caddy routes, then reload Caddy.
8. Verify authentication and exact public tool schemas.
9. Prove every Life mutation/cross-project attempt is denied.
10. Create, edit, move, and delete a canary note only in
    `phase2-verification`; confirm final absence.
11. Rehearse stopping/restarting the new stack and verify the legacy endpoint.

Run private backend validation with:

```bash
docker compose --profile tools run --rm validator
```

The validator prints result titles, permalinks, scores, tool names, and hashes;
it does not print note bodies or credentials.

## Rollback

The legacy deployment is not modified by this Compose project. If Phase 2 fails:

1. Remove only the two new Caddy host blocks, validate, and reload Caddy.
2. Run `docker compose stop`; do not use `down -v`.
3. Retain new state volumes for diagnosis.
4. Recheck `https://dktzr-n8n.duckdns.org/mcp` authentication and legacy health.

DNS and disabled OAuth applications may remain reserved until an explicit
cleanup decision.
