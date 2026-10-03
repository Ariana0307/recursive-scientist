# Minimal interfaces (schema_version 0.1.0)

This is a contract proposal maintained by control, not an implemented runner or an Omnigent configuration. All objects require schema_version and experiment_id (nonempty unique run identifier). JSON numbers must be finite; unavailable values are null, never invented.

## ExperimentConfig

Required: schema_version:string; experiment_id:string; seed:integer; config:object (all resolved experiment parameters); status:`proposed` or `approved`; code_version:string (full Git commit); config_hash:string (sha256 of canonical config); validation:object (metric names, split identifier, objective direction); runtime:object (requested limits: timeout_seconds and device_class).

## Result

Required: schema_version; experiment_id; seed; config; config_hash; code_version; status:`succeeded`, `failed`, `cancelled` or `timed_out`; validation:object (metrics mapping metric names to number or null, split identifier); runtime:object (elapsed_seconds:number|null, started_at and finished_at:ISO8601 timezone timestamps|null, actual_device:string|null); error:object|null (kind and sanitized message).

Failed/non-success results have error details and no success accuracy; metrics not measured are null. Partial metrics must be explicitly labelled and cannot imply successful completion. Config identity must match the submitted ExperimentConfig.

## Decision

Required: schema_version; experiment_id (source experiment); seed; config (proposed next resolved configuration); config_hash; code_version (decision implementation); status:`propose_next`, `stop` or `needs_review`; validation:object (observed metrics or null, objective); runtime:object (decision elapsed_seconds:number|null); rationale:string; evidence_result_id:string; next_experiment_id:string|null; strategy_version:string.

## Identity and hashing

Use RFC 8785 JSON canonicalization for the `config` object only; UTF-8 bytes, SHA-256 lowercase 64 hex characters. Store seed and all resolved parameters in config too, so seed changes change the hash. Reject inconsistent duplicated seed/config fields. No canonicalization implementation is claimed in Gate 0. Code versions are full commit hashes; dirty code must be identified and cannot silently claim a clean commit. Keep paths and credentials out of public payloads.
