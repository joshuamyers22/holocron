# Security Policy

Report vulnerabilities privately to `joshuamyers22` through GitHub's private
vulnerability-reporting channel. Do not open a public issue containing exploit
details, credentials, sensitive data, or unpatched statistical-integrity defects.
The target is acknowledgement within three business days, initial severity and
scope triage within seven business days, and a remediation plan within fourteen
business days. These are response targets, not a guaranteed fix deadline.

Do not include real credentials or production data in reports or reproductions.
The project has no public release or hosted service; if that changes, incident
escalation, supported-version, and disclosure timelines require review.

Treat statistical model risk as a correctness and governance concern: preserve
the approved sample and specification, restrict sensitive outputs, test leakage
and unstable assumptions, and require review before a result affects capital,
risk limits, client reporting, or automated decisions.

See `governance/THREAT_MODEL.md` for the current trust boundaries and abuse
cases. Suspected GPL/provenance contamination is handled privately as a
release-blocking integrity incident.
