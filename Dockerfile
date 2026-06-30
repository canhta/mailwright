# Match the tag to your installed playwright version (uv run playwright --version).
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cache-friendly)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source
COPY src ./src

# The Playwright image already ships browsers; ensure chromium is present.
RUN uv run playwright install chromium

ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "python", "-m", "mailwright.cli", "agent"]
