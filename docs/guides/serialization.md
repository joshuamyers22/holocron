# Serialization and reconstruction

Holocron's supported persistence format is canonical, versioned JSON. It stores
data only: loading never imports a class named by a document or evaluates a
formula, callback, or expression.

```python
# holocron: execute
from holocron.design import DesignMatrix, DesignSpec
from holocron.models import OlsResult, fit_ols

specification = DesignSpec.from_formula("y ~ pol(x, 2)")
matrix = specification.transform({"x": (-2, -1, 0, 1, 2)})
fit = fit_ols((5, 2, 1, 2, 5), matrix)

restored_specification = DesignSpec.from_json(specification.to_json())
restored_matrix = DesignMatrix.from_json(matrix.to_json())
restored_fit = OlsResult.from_json(fit.to_json())

assert restored_specification == specification
assert restored_matrix == matrix
assert restored_fit == fit
assert restored_fit.design_fingerprint == specification.fingerprint
assert restored_fit.predict(restored_matrix) == restored_fit.fitted_values
```

`to_dict()` returns the schema document, `to_json()` returns its canonical JSON,
and `fingerprint` is the SHA-256 digest of that JSON. `from_dict()` and
`from_json()` accept exact current versions only. They reject extra or missing
fields and recheck invariants that JSON Schema cannot express.

## Finding the installed schemas

The wheel includes the contracts as package data:

```python
from importlib.resources import files

schema_directory = files("holocron").joinpath("schemas")
manifest = schema_directory.joinpath("serialization-manifest.json")
assert manifest.is_file()
```

The manifest identifies every serializable public type, version, and schema
filename. The current readers limit JSON text to 64 MiB; design matrices and
results additionally impose documented row and column limits.

Do not persist Holocron objects with pickle as a supported interchange format.
Do not treat fingerprints as signatures. Store the exact schema version with
the document, validate untrusted input, and protect result documents as
potentially sensitive because fitted values and residuals are input-derived.

See [ADR-008](../adr/ADR-008-model-result-serialization.md) for compatibility
and migration rules.
