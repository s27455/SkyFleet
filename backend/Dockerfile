# SkyFleet backend image, shared by the `migrate`, `api` and `worker` Compose services.
FROM python:3.13-slim

# uv, pinned, copied from its official image (installs the locked dependencies).
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

# The virtual environment lives outside /app; the image's own Python 3.13 is used (no download).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first (cached layer), exactly as locked in uv.lock; dev tools are not installed.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev

COPY . .

EXPOSE 8000
# Default command: the API. Compose overrides it for `migrate` and `worker`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
