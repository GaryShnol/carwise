# Docker (CW-402)

## Run

```bash
docker build -t carwise .
docker run --rm -e OPENAI_API_KEY -v carwise-data:/app/data -p 8501:8501 carwise
```

- `-e OPENAI_API_KEY` passes the key from your shell by name: it is not typed on the command
  line, not stored in the image, and never a build argument. (`-e OPENAI_API_KEY=sk-...` also
  works, but leaves the key in your shell history.)
- `-v carwise-data:/app/data` is a named volume for the articles, the embedding model and the
  index. Keep it between runs; delete it (`docker volume rm carwise-data`) to start over.
- `-p 8501:8501` publishes the UI on http://localhost:8501. Inside the container Streamlit
  listens on 0.0.0.0, because only the published port is reachable from the host. Outside
  Docker, `python -m app ui` listens on localhost only.
- `-e CARWISE_PROFILE=final` selects the `final` profile (default `dev`).

The app is meant to run locally with your own API key. The cost cap
(`llm.max_cost_usd`) bounds one conversation (one browser session), not the process.

## First start

The image holds no articles, model or index. At the first page load the UI:

1. fetches the eight articles with the polite fetcher (identifiable User-Agent, a delay
   between requests, `robots.txt` respected) into `/app/data/raw`;
2. downloads the pinned embedding model into `/app/data/huggingface`;
3. builds the index in `/app/data/index`,

while the page shows its loading message. Later starts reuse the volume and take seconds.
If the site blocks the download, the page says so in Hebrew; the articles can then be put in
the volume's `raw/` folder by hand (for example with `docker cp`) and the page refreshed.

Measured on the development machine (Windows 11, Docker Desktop, 12 CPU threads, home
connection), 2026-10-31:

| | |
|---|---|
| Image size | 2.18 GB (torch CPU 0.8 GB; most of the rest is transitive: chromadb pulls kubernetes and onnxruntime, streamlit pulls pyarrow and pandas) |
| Build, base images already pulled | about 1 min 40 s |
| First start, page open until the chat is ready | 177 s (eight articles, 2.2 GB model download, index build) |
| Later start on the same volume | 17 s (model loaded from the volume) |
| First answer after the chat is ready | about 4 s (`dev` profile) |
| Volume after the first start | model 2.2 GB, articles 1.9 MB, index 2.7 MB |

## What the image contains, and what it does not

- Base: `python:3.13.18-slim`, pinned by digest; a two-stage build, so uv and the build cache
  stay out of the runtime image. Dependencies are exactly `uv.lock` (`uv sync --locked
  --no-dev`), with the CPU build of torch (no CUDA libraries).
- Runs as the non-root user `carwise` (uid 10001); `/app/data` and `/app/logs` are its only
  writable folders.
- `HEALTHCHECK` polls Streamlit's `/_stcore/health`, which answers as soon as the server is up,
  also while the first start is still indexing.
- `.dockerignore` is an allow-list (`pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`, `src/`,
  `app/`, `eval/`, `config/`), and inside it excludes `.env*`, keys, `data/`, `logs/`,
  `eval/runs/`, `.git/`, `.venv/` and caches. `tests/test_docker.py` checks these rules, the
  non-root user, the missing build arguments and the command, without Docker.
- Turn logs go to `/app/logs` inside the container (lost with it); they hold no message text
  and no key.
