# Reference Source

Holocron's initial statistical specification source is the read-only local
snapshot `/Users/josh/Downloads/rms-master`.

## Verified identity

- Package: `rms`
- Version: `8.2-0`
- Date: `2026-09-11`
- License declared by the source: `GPL (>= 2)`
- Required R version: `>= 4.4.0`
- Required Hmisc version: `>= 5.3-0`
- Matching upstream commit: `a4e4a305a029090e737562fb4d35bdb705db7d63`
- Inventory: 102 files under `R/`, 108 files under `man/`, 129 files under
  `inst/tests/`, eight top-level native files and one Ratfor file under `src/`;
  363 files and 2,505,213 bytes total
- File-manifest SHA-256:
  `40a3805d92ecd6bd1318db842c8c78e05595e48345b46c5e9e21ef01cd7a0bce`

| File | SHA-256 |
|---|---|
| `DESCRIPTION` | `0528cd8378601f0b05a6e6fb3daa89e8dfc6211adb82246c2f4eb7dec12ae23b` |
| `NAMESPACE` | `db1cc94792cceaca300e00e38229580349b3d93ee18493f6097d7ae91f63ef6b` |
| `NEWS` | `84cd6605bee5ec3c7314533e89f6a5bfb0429038140438462389ea1566f5c912` |
| `copyright` | `c12bef243759f6ce1078c448535eeaa26e2889fa8456c5ff43b43202f5af8e75` |

Verified locally on 2026-09-17. Although the snapshot is not a Git checkout, a
recursive comparison excluding Git metadata found it byte-identical to upstream
commit `a4e4a305a029090e737562fb4d35bdb705db7d63`, committed 2026-09-14. Upstream
had no `8.2-0` tag at verification time, so the commit and complete file manifest
jointly define the immutable source. See
`reference/manifests/rms-8.2-0-inventory.json` and ADR-003.

## Use policy

The snapshot is reference material, not vendored project code. Do not copy or
mechanically translate its R, C, Fortran, documentation, or tests into Holocron
unless ADR-001 and the selected distribution license explicitly permit that use.
The independent implementation must use project-authored Python code and
project-authored parity cases under the approved provenance workflow.
