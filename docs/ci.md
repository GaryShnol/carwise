# CI and repository settings (CW-403)

## What runs, and when

| Workflow | Trigger | What | Network | Secrets |
|---|---|---|---|---|
| `ci.yml` | push to `main` or `epic/**`, pull request to `main` | `ruff check`, `ruff format --check`, `mypy`, `pytest` on Python 3.11 and 3.13 | package install only; tests are offline (`HF_HUB_OFFLINE=1`) | none |
| `eval.yml`, level `retrieval` | manual (`workflow_dispatch`) | ingest, the tests that need the articles or the real model, the retrieval eval | fetches the articles and the model on a cache miss | none |
| `eval.yml`, level `answer` | manual (`workflow_dispatch`) | ingest, the answer eval on `dev` or `final` | as above, plus the OpenAI API | `OPENAI_API_KEY`, only in the eval step |
| `docker.yml` | manual (`workflow_dispatch`) | build the image, then inside it (`--network none`, no environment) load `config/settings.yaml` and `config/cars.yaml` | base images and packages for the build only | none |

- The unit tests use synthetic chunks, a fake embedder and a fake LLM. Tests that need the
  articles skip without them; they run in the manual retrieval job.
- The answer eval costs money and is never automatic. Its spend is capped by
  `eval.answer_max_cost_usd` and `eval.judge_max_cost_usd` in `config/settings.yaml`. Without
  the secret the job ends with a notice and spends nothing.
- Caches: the embedding model by name and pinned revision; the articles by the hash of
  `config/cars.yaml`. The articles are fetched with the polite fetcher on a miss. If the site
  blocks the runner, ingest fails with its message and the job fails; it is not worked around.
- Uploaded artifacts: `eval/reports/` only (chunk ids, scores, checks, costs), kept 14 days.
  `eval/runs/` holds answer text and is never uploaded.
- Linux installs take the CPU build of torch (`[tool.uv.sources]` in `pyproject.toml`), which
  keeps about 3 GB of CUDA libraries out of CI and the Docker image.

## Security choices

- `permissions: contents: read` in both workflows; checkout with `persist-credentials: false`.
- Every action pinned to a full commit SHA, with the version in a comment. uv itself is pinned
  (`0.13.1`), and `uv sync --locked` fails if `uv.lock` does not match `pyproject.toml`.
- Pull requests from forks use the `pull_request` event: read-only token, no secrets, and
  `ci.yml` uses none. No workflow uses `pull_request_target`.
- `workflow_dispatch` can be started only by people with write access, so the API key is never
  exposed to a fork. Dispatch inputs are a choice and a number, and they reach the shell as
  environment variables, never pasted into the script.
- Known limit: a fork pull request runs its own copy of the workflow files, and it can restore
  caches created on `main`, which includes the cached articles (public on the publisher's site
  anyway). The "require approval" setting below keeps such a run from starting unreviewed.

## Settings to apply on GitHub (owner)

These need the repository admin; they cannot be set from a commit.

### 1. Branch protection for `main`

Settings → Branches → Add classic branch protection rule, branch name pattern `main`:

- [x] Require a pull request before merging
  - Required approvals: **0** (a single-author repository; 1 would block every merge)
  - [x] Dismiss stale pull request approvals when new commits are pushed
- [x] Require status checks to pass before merging
  - [x] Require branches to be up to date before merging
  - Required checks (they appear in the search box after `ci.yml` has run once on a branch):
    - `lint, types, unit tests (py3.11)`
    - `lint, types, unit tests (py3.13)`
- [x] Require conversation resolution before merging
- [ ] Require signed commits (off: not used in this repository)
- [ ] Require linear history (**off**: epics are merged with a merge commit, never squashed)
- [x] Do not allow bypassing the above settings
- [ ] Allow force pushes (off)
- [ ] Allow deletions (off)

The same rule from the command line (needs `gh` logged in as an admin):

```bash
gh api -X PUT repos/GaryShnol/carwise/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "lint, types, unit tests (py3.11)",
      "lint, types, unit tests (py3.13)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON
```

### 2. Actions settings

Settings → Actions → General:

- Actions permissions: **Allow GaryShnol, and select non-GaryShnol, actions and reusable
  workflows**, then tick **Allow actions created by GitHub** and add `astral-sh/setup-uv@*` under
  "Allow specified actions". That covers `actions/checkout`, `actions/cache`,
  `actions/upload-artifact` and `setup-uv`, and nothing else. (The SHAs are pinned either way.)
- Fork pull request workflows from outside collaborators: **Require approval for all external
  contributors**.
- Workflow permissions: **Read repository contents and packages permissions**.
- [ ] Allow GitHub Actions to create and approve pull requests (off).

### 3. The API key (optional, only for the manual answer eval)

Settings → Secrets and variables → Actions → New repository secret: `OPENAI_API_KEY`.
Use a key from a separate OpenAI project with a low monthly budget limit, so a mistake in the
workflow cannot spend more than that limit.
