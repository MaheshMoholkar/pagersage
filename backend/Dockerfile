FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so code edits don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Editable install keeps pagersage/ next to queries/, which the query loader relies on.
COPY pagersage ./pagersage
COPY queries ./queries
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 app && chown -R app /app
USER app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "pagersage.main:app", "--host", "0.0.0.0", "--port", "8000"]
