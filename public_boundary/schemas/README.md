# Public Bridge Schemas

This directory contains public contract fixtures for approved Viewledge
clients. The schemas describe product concepts and opaque identifiers only;
they do not prescribe a server language, storage layout, processing engine, or
model service.

`bridge_api_v1.schema.json` is versioned independently from the private core.
Compatible clients must send and validate `schema_version: "1.0"`. A private
implementation may support this contract, but a public client must not import
private packages or infer their behavior from implementation details.

Public releases are produced from a reviewed allowlist into a clean staging
directory. This directory is a contract source, not a public repository and
does not authorize publication by itself.
