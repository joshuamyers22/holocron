# Installation

Holocron is available only from its private source repository. It has not been
published to PyPI, and external distribution is blocked pending qualified
license and provenance review.

## Supported development environment

The canonical evidence environment uses CPython 3.12.14 and uv 0.12.7. Package
metadata permits Python 3.11 or later, but installability alone is not a parity
claim. The accepted numerical envelope is documented in
[ADR-009](adr/ADR-009-supported-numerical-envelope.md).

From a repository checkout:

```sh
make setup
make check
```

`make setup` verifies the lock before synchronizing it. `make check` is offline
after setup and covers formatting, static types, tests, executable documentation,
a strict site build, frozen-environment identities, and reference metadata.

## Local library use

The setup target installs an editable `holocron-rms` distribution into `.venv`.
The import package is `holocron`:

```python
# holocron: execute
import holocron

assert holocron.__version__ == "0.1.0"
```

There is no command-line interface and no runtime R dependency. The isolated R
oracle is a development verifier only; see the
[independent-oracle decision](adr/ADR-001-independent-oracle.md).
