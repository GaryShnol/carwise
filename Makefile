.PHONY: ingest chat ui eval test lint docker

# Thin wrappers: the real entry point is `python -m app <command>`,
# so everything also works in PowerShell without make.
ingest:
	uv run python -m app ingest

chat:
	uv run python -m app chat

ui:
	uv run python -m app ui

eval:
	uv run python -m app eval

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src app eval

docker:
	@echo "Dockerfile arrives with CW-402."; exit 1