/**
 * Client-side upload size gates.
 *
 * These MIRROR the server caps enforced by `read_upload_capped()` in
 * `backend/utils/uploads.py`. They exist only so the user gets an
 * immediate, named toast instead of a round-trip 413 after uploading
 * 80 MB — the server remains the authority. If you change a value here,
 * change the matching constant in the router that owns the endpoint.
 */

/** findings / testcases / engagements `/evidence` — matches MAX_EVIDENCE_BYTES. */
export const MAX_EVIDENCE_BYTES = 100 * 1024 * 1024; // 100 MB

/** `/intel/items/{id}/attachments` — matches MAX_INTEL_ATTACHMENT_BYTES. */
export const MAX_INTEL_ATTACHMENT_BYTES = 50 * 1024 * 1024; // 50 MB

/** `/vault/upload` and `/infra/items/{id}/vault/upload` — matches MAX_VAULT_FILE_BYTES. */
export const MAX_VAULT_FILE_BYTES = 25 * 1024 * 1024; // 25 MB
