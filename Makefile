PYTHON ?= python3
PYTHON_IMAGE ?= python:3.14-slim

.PHONY: format lint test build ci ci-docker

format:
	$(PYTHON) -m isort src tests
	$(PYTHON) -m black src tests

lint:
	$(PYTHON) -m black --check src tests
	$(PYTHON) -m isort --check-only src tests
	$(PYTHON) -m flake8 src tests

test:
	$(PYTHON) -m pytest --cov=govdomains --cov-report=term-missing

build:
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

ci: lint test build

ci-docker:
	docker run --rm -v "$(CURDIR):/source:ro" -w /tmp/project $(PYTHON_IMAGE) sh -ec 'apt-get update -qq; apt-get install -y -qq --no-install-recommends make; cp -R /source/src /source/tests /source/pyproject.toml /source/README.md /source/LICENSE /source/.flake8 /source/Makefile .; pip install ".[dev]"; make ci'
