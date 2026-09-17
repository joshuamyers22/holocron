.PHONY: setup format lint typecheck test check audit build oracle-build oracle-health oracle-check
setup:
	uv sync --frozen --dev
format:
	uv run ruff format .
lint:
	uv run ruff check .
	uv run ruff format --check .
typecheck:
	uv run pyright
test:
	uv run python -m unittest discover -s tests
check: lint typecheck test
audit:
	uv audit --preview-features audit-command --locked --no-dev
	uv run python tools/check_licenses.py
build:
	uv build

oracle-build:
	@test -n "$(RMS_SOURCE)" || (echo "usage: make oracle-build RMS_SOURCE=/absolute/path/to/rms-master"; exit 2)
	reference/r/build-oracle.sh "$(RMS_SOURCE)"

oracle-health:
	printf '%s\n' '{"operation":"health"}' | reference/r/run-oracle.sh

oracle-check:
	uv run python reference/check_oracle.py
