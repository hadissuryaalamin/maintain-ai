# Security policy

This is a portfolio demonstration, not certified safety software and not an equipment-control
system. Do not connect it to machinery or load real maintenance data without a separate security,
privacy, and functional-safety review.

Please use the repository's
[private vulnerability report](https://github.com/hadissuryaalamin/maintain-ai/security/advisories/new)
rather than opening a public issue. Include the affected revision, reproducible steps, impact,
and suggested mitigation if known. Do not include secrets, personal data, or data from systems
you do not own. If GitHub private vulnerability reporting is unavailable, contact the repository
owner privately before sharing sensitive details.

The local `X-Tenant-ID` / `X-User-ID` header adapter is intentionally non-production. A real
deployment must verify identity cryptographically and construct the authoritative tenant context
server-side.
