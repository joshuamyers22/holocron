# Data-distribution metadata

`DataDistribution` records the predictor summaries later design, prediction,
effect, and plotting APIs will need. It is immutable and explicit: no global
option or original dataframe is consulted after construction.

```python
# holocron: execute
from holocron.design import DataDistribution, DistributionRange

age = (30, 34, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74)
group = ("A", "B", "A", "B", "A", "B", "A", "B", "A", "B", "A", "B")

distribution = DataDistribution.from_data(
    {"age": age, "group": group},
    levels={"group": ("A", "B")},
    labels={"age": "Age", "group": "Treatment group"},
    units={"age": "years"},
)

assert distribution.names == ("age", "group")
assert distribution.adjustments == {"age": 52.0, "group": "A"}
assert distribution["age"].effect_range == DistributionRange(41.0, 63.0)
assert distribution["group"].values == ("A", "B")
assert DataDistribution.from_json(distribution.to_json()) == distribution
```

## Summary rules

- Numeric variables use the lower value for binary adjustment, the middle value
  for three unique values, and the median otherwise.
- Effect limits default to the 0.25 and 0.75 quantiles.
- Display limits default to the 0.05 and 0.95 quantiles below 200 non-missing
  observations; at larger sizes they select the probability corresponding to
  the tenth observation from each end.
- Numeric variables at or below the discrete threshold retain their sorted
  unique values. Constant variables retain a single value and constant ranges.
- `None` and NaN are counted as missing and excluded from numeric summaries.
  Infinite values are rejected.
- Unordered categorical variables use the modal level, breaking ties by the
  declared level order. `categorical_adjustment="first"` selects the first
  declared level instead.
- Ordered variables use the declared middle level and full declared range.

Use `with_adjustment` to create a copy with a different reference value and
`with_data` to append new same-row-count columns under the original policies.
The canonical JSON form is versioned and its `fingerprint` is a SHA-256 identity
for provenance records.

## Boundary

All columns must have equal length. Categorical levels must be declared; this
prevents row ordering from silently defining category ordering. Labels and units
are metadata only and do not perform conversion. The formula engine is now
available, but automatic use of distribution metadata for knot or adjustment
selection, dataframe/date-time adapters, and model-level missing-data behavior
remain outside this capability.

The exact supported envelope and deliberate differences from R are recorded in
the [compatibility inventory](../compatibility.md) and
[acceptance record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_DATA_DISTRIBUTION.md).
