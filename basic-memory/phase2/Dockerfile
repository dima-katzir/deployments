ARG BASIC_MEMORY_IMAGE=ghcr.io/basicmachines-co/basic-memory:0.22.1@sha256:0da35f465fed7b58b6c2e31e7c0dbcbc728760a1b6a71857cfe3ced847c727a1

FROM ${BASIC_MEMORY_IMAGE} AS backend
USER root
COPY --chown=appuser:appuser backend_health.py validate_backends.py /app/
USER appuser

FROM ${BASIC_MEMORY_IMAGE} AS gateway
USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache 'py-key-value-aio[disk]==0.4.4'
COPY --chown=appuser:appuser gateway_common.py gateway_life_os.py gateway_general.py /app/
USER appuser
