PYTHON_IMAGE ?= python:3.14-slim

.PHONY: format lint test docs build check ci ci-docker

format:
	uv run ruff check --fix
	uv run ruff format

lint:
	uv run ruff check
	uv run ruff format --check
	uv run pyright
	uvx pydoclint==0.9.1 --config pyproject.toml src scripts

test:
	uv run pytest --cov --cov-report=term-missing

docs:
	uv run sphinx-build -W --keep-going -b html docs docs/_build/html
	uv run sphinx-build -W --keep-going -b doctest docs docs/_build/doctest

build:
	uv build
	uvx twine check dist/*

check:
	uvx preen check --strict --explain

ci: lint test docs build

ci-docker:
	docker run --rm -v "$(CURDIR):/source:ro" -w /tmp/project $(PYTHON_IMAGE) sh -ec 'apt-get update -qq; apt-get install -y -qq --no-install-recommends make git; pip install uv; tar -C /source --exclude=.git --exclude=.venv --exclude=dist --exclude=build --exclude=_build --exclude=__pycache__ -cf - . | tar -xf -; uv sync --frozen --all-groups; make ci'
