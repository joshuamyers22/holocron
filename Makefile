.PHONY: setup lock-check format lint typecheck test docs docs-generate docs-check frozen-environments frozen-environments-live reference-metadata tolerance-pilot phase-1-e2e phase-1-exit-gate phase-2-evidence phase-2-exit-gate phase-3-evidence phase-3-evidence-clean phase-4-evidence phase-4-evidence-clean phase-5-evidence phase-5-evidence-clean check audit build clean-build oracle-build oracle-health oracle-check reference-source-check
setup:
	uv lock --check
	uv sync --frozen --dev --no-install-project
	uv sync --frozen --dev --no-build-isolation
lock-check:
	uv lock --check
format:
	uv run --frozen ruff format .
lint:
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .
typecheck:
	uv run --frozen pyright
test:
	uv run --frozen python -m unittest discover -s tests
docs:
	uv run --frozen mkdocs serve
docs-generate:
	uv run --frozen python tools/generate_docs.py
docs-check:
	uv run --frozen python tools/generate_docs.py --check
	uv run --frozen python tools/check_docs_examples.py
	uv run --frozen mkdocs build --strict --clean
frozen-environments:
	uv run --frozen python tools/check_frozen_environments.py
frozen-environments-live:
	uv run --frozen python tools/check_frozen_environments.py --live-r-oracle
reference-metadata:
	uv run --frozen python -m tools.check_reference_metadata
tolerance-pilot:
	uv run --frozen python -m tools.run_tolerance_pilot
phase-1-e2e:
	uv run --frozen python -m tools.run_phase_1_vertical_slice
phase-1-exit-gate:
	uv run --frozen python -m tools.run_phase_1_vertical_slice --require-clean
phase-2-evidence:
	uv run --frozen python -m tools.run_phase_2_exit_gate
phase-2-exit-gate:
	uv run --frozen python -m tools.run_phase_2_exit_gate --require-clean
phase-3-evidence:
	uv run --frozen python -m tools.run_phase_3_evidence
phase-3-evidence-clean:
	uv run --frozen python -m tools.run_phase_3_evidence --require-clean
phase-4-evidence:
	uv run --frozen python -m tools.run_phase_4_evidence
phase-4-evidence-clean:
	uv run --frozen python -m tools.run_phase_4_evidence --require-clean
phase-5-evidence:
	uv run --frozen python -m tools.run_phase_5_simulations
phase-5-evidence-clean:
	uv run --frozen python -m tools.run_phase_5_simulations --require-clean
check: lock-check lint typecheck test docs-check frozen-environments reference-metadata phase-1-e2e phase-2-evidence phase-3-evidence phase-4-evidence phase-5-evidence
audit:
	uv audit --preview-features audit-command --locked --no-dev
	uv run --frozen python tools/check_licenses.py
build:
	uv run --frozen python tools/build_and_smoke_artifacts.py --output-directory dist
clean-build:
	uv run --frozen python tools/build_and_smoke_artifacts.py --output-directory dist --require-clean

oracle-build:
	@test -n "$(RMS_SOURCE)" || (echo "usage: make oracle-build RMS_SOURCE=/absolute/path/to/rms-master"; exit 2)
	reference/r/build-oracle.sh "$(RMS_SOURCE)"

oracle-health:
	printf '%s\n' '{"operation":"health"}' | reference/r/run-oracle.sh

oracle-check:
	uv run --frozen python -m reference.check_oracle

reference-source-check:
	@test -n "$(RMS_SOURCE)" || (echo "usage: make reference-source-check RMS_SOURCE=/absolute/path/to/rms-master"; exit 2)
	uv run --frozen python tools/build_reference_inventory.py "$(RMS_SOURCE)" --check
