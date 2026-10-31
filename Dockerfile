# carwise: the Hebrew Streamlit chat in one container (CW-402).
#
#   docker build -t carwise .
#   docker run --rm -e OPENAI_API_KEY -v carwise-data:/app/data -p 8501:8501 carwise
#
# What is NOT in the image, on purpose:
# - the articles: they belong to the publisher; the app fetches them politely at
#   first start into the volume (or they can be placed in its data/raw by hand);
# - the embedding model (about 2 GB) and the index: built at first start into the
#   volume, so the image stays small and a second start takes seconds;
# - the API key: passed at run time with -e, never as a build argument or ENV.

# --- build: resolve exactly uv.lock into a virtual environment ----------------------
FROM python:3.13.18-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app

# Dependencies first (a layer that changes only with the lock file). On Linux torch
# comes from the PyTorch CPU index ([tool.uv.sources], CW-403): no CUDA libraries.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project

# Then the package itself, installed editable from /app/src, the same layout as a
# checkout: config/settings.yaml and config/cars.yaml are found next to src/.
COPY src ./src
RUN uv sync --locked --no-dev

# --- runtime: the venv, the app code and config; no uv, no build tools --------------
FROM python:3.13.18-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # The model downloads into the volume, next to the articles and the index.
    HF_HOME=/app/data/huggingface \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin carwise
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY src ./src
# app/ and eval/ are run from the working directory (`python -m app`); eval/ is
# needed because the entry point registers the eval command. Only committed files.
COPY app ./app
COPY eval ./eval
COPY config ./config
# Owned by the app user: a new named volume mounted at /app/data takes this ownership.
RUN mkdir -p /app/data /app/logs && chown carwise:carwise /app/data /app/logs

USER carwise
VOLUME ["/app/data"]
EXPOSE 8501

# Streamlit answers /_stcore/health as soon as its server is up, also while the
# first start is still downloading and indexing (the page shows that as loading).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"]

# 0.0.0.0 inside the container only: the host decides what to publish with -p.
CMD ["python", "-m", "app", "ui", "--address", "0.0.0.0", "--port", "8501", "--ingest-if-missing"]
