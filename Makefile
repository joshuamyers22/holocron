.PHONY: setup format lint typecheck test reference-metadata check audit build oracle-build oracle-health oracle-check reference-source-check
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
reference-metadata:
	uv run python tools/check_reference_metadata.py
check: lint typecheck test reference-metadata
audit:
	uv audit --preview-features audit-command --locked --no-dev
	uv run python tools/check_licenses.py
build:
	uv build
	uv run python tools/check_build_artifacts.py

oracle-build:
	@test -n "$(RMS_SOURCE)" || (echo "usage: make oracle-build RMS_SOURCE=/absolute/path/to/rms-master"; exit 2)
	reference/r/build-oracle.sh "$(RMS_SOURCE)"

oracle-health:
	printf '%s\n' '{"operation":"health"}' | reference/r/run-oracle.sh

oracle-check:
	uv run python reference/check_oracle.py

reference-source-check:
	@test -n "$(RMS_SOURCE)" || (echo "usage: make reference-source-check RMS_SOURCE=/absolute/path/to/rms-master"; exit 2)
	uv run python tools/build_reference_inventory.py "$(RMS_SOURCE)" --check
