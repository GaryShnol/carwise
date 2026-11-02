# Docker (CW-402)

## Run

With Docker Compose (recommended):

```bash
cp .env.example .env    # then fill in OPENAI_API_KEY, or export it (PowerShell: copy .env.example .env)
docker compose up --build    # or: make docker-up
```

- `compose.yaml` takes `OPENAI_API_KEY` from your shell or from `.env` next to it; a shell value
  overrides the file. The key is never written in `compose.yaml`, and a missing or empty key
  stops compose before anything starts, with the message
  `set OPENAI_API_KEY in your shell or in a .env file`.
- It publishes the UI on `127.0.0.1` only (see the `-p` note below) at http://localhost:8501,
  mounts the same `carwise-data` volume as the command below, and keeps the image's
  `HEALTHCHECK`.
- The first start takes about 3 minutes (177 s measured below: the eight articles, the 2.2 GB
  model download and the index build); later starts reuse the volume.
- `docker compose down` stops and removes the container and keeps the volume;
  `docker volume rm carwise-data` starts over.
- `CARWISE_PROFILE=final` in the shell or in `.env` selects the `final` profile (default `dev`).
- Every compose command (`ps`, `logs`, `down`) reads `compose.yaml` and so needs the key too;
  with the key in `.env` that is automatic. If the volume was first made without compose,
  compose warns that it "was not created by Docker Compose"; the warning is harmless.

Without compose, with the key set in your shell:

```bash
docker build -t carwise .
docker run --rm -e OPENAI_API_KEY -v carwise-data:/app/data -p 127.0.0.1:8501:8501 carwise
```

- `-e OPENAI_API_KEY` passes the key from your shell by name: it is not typed on the command
  line, not stored in the image, and never a build argument. (`-e OPENAI_API_KEY=sk-...` also
  works, but leaves the key in your shell history.)
- `-v carwise-data:/app/data` is a named volume for the articles, the embedding model and the
  index. Keep it between runs; delete it (`docker volume rm carwise-data`) to start over.
- `-p 127.0.0.1:8501:8501` publishes the UI on the host's loopback address only, at
  http://localhost:8501, so other machines on the network cannot reach it. Without the
  `127.0.0.1:` part Docker publishes the port on every interface of the
  host, and on Linux its firewall rules bypass ufw. The UI has no login, and every question
  is paid for with your API key. Inside the container Streamlit listens on 0.0.0.0, because
  only the published port is reachable from the host. Outside Docker, `python -m app ui`
  listens on localhost only.
- `-e CARWISE_PROFILE=final` selects the `final` profile (default `dev`).

The app is meant to run locally with your own API key. Two cost caps apply:
`llm.max_cost_usd` ($2.00) bounds one conversation (one browser session), and a refresh starts
a new one; `llm.max_total_cost_usd` ($5.00) bounds every session of the running server
together, and only a restart resets it. Calls already in flight when the total is reached
still finish, so the total can pass it by at most one call per active session.

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
- Turn logs go to `/app/logs` inside the container (lost with it); they hold no user words
  (no message text, unknown car names only as a count) and no key.
