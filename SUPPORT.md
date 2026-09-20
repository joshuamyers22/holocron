# Support policy

Holocron is currently a private, experimental package at version 0.1.0. There
is no supported public release, production service, availability commitment, or
response-time service-level agreement. The policy below takes effect only when
an externally authorized stable release is published.

## Supported releases

- The newest patch of the current stable minor release receives defect,
  security, compatibility, and documentation fixes.
- The newest patch of the immediately preceding stable minor release receives
  critical statistical-correctness and security fixes for six months after the
  next minor release.
- Release candidates receive evaluation support only and may be superseded
  without a migration window. Development snapshots and older releases are not
  supported.
- Python 3.11 and 3.12 are the supported installation matrix for the planned
  1.0 line. Only the narrower environments declared by ADR-009 carry numerical
  parity claims; installability does not imply parity on every platform or BLAS.

The release notes and compatibility inventory define the supported capability
surface. Mapped or intentionally unsupported R APIs are not promoted merely by
appearing in the inventory. A request outside the documented surface receives
a clear unsupported disposition rather than a silent approximation.

## Getting help

Use the repository issue tracker for reproducible usage, installation,
documentation, and compatibility reports. Include the Holocron version, Python
version, operating system, minimal synthetic reproducer, observed result, and
expected result. Do not submit private, clinical, client, credential, or other
restricted data.

Security reports follow `SECURITY.md` and must not be filed publicly. The
maintainer and support owner is `joshuamyers22` until an approved governance
record assigns another owner.

For supported releases, the project targets initial triage within:

- two business days for suspected security or statistical-correctness defects;
- five business days for installation or documented-compatibility regressions;
- ten business days for other supported questions.

These are triage targets, not resolution guarantees. Reports lacking a safe
reproducer or falling outside the supported surface may be returned for more
information or closed as unsupported.

## Compatibility and lifecycle

Confirmed regressions are classified by user impact. Critical statistical or
security defects block promotion and may require a patch release, withdrawal,
or explicit do-not-use notice. Other fixes follow semantic versioning: patches
preserve the public statistical contract, minors may add qualified capability,
and majors may intentionally change it. Numerical changes still require the
applicable parity evidence.

Ordinary public API removals follow the deprecation policy: a visible warning,
a documented replacement, changelog and migration guidance, at least two minor
releases, and at least 90 days. Security or correctness emergencies may shorten
that period when the release response record explains why.

End-of-support dates are announced in release notes and the changelog. An
unsupported release remains available only at the project's discretion and
receives no fixes. Artifact withdrawal, vulnerability response, and emergency
compatibility procedures are governed by the separate Phase 9 response
runbooks; until those runbooks are complete, stable release remains blocked.
