PYTHON ?= python3
PYTHON_IMAGE ?= python:3.14-slim

.PHONY: format lint test build ci ci-docker

format:
	$(PYTHON) -m isort src tests scripts
	$(PYTHON) -m black src tests scripts

lint:
	$(PYTHON) -m black --check src tests scripts
	$(PYTHON) -m isort --check-only src tests scripts
	$(PYTHON) -m flake8 src tests scripts

test:
	$(PYTHON) -m pytest --cov=govdomains --cov-report=term-missing

build:
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

ci: lint test build

ci-docker:
	docker run --rm -v "$(CURDIR):/source:ro" -w /tmp/project $(PYTHON_IMAGE) sh -ec 'apt-get update -qq; apt-get install -y -qq --no-install-recommends make; cp -R /source/src /source/tests /source/scripts /source/pyproject.toml /source/README.md /source/LICENSE /source/.flake8 /source/Makefile /source/MANIFEST.in /source/CHANGELOG.md /source/SPEC.md .; mkdir data; cp /source/data/README.md data/; pip install ".[dev]"; make ci'
