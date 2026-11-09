/**
 * Record fields that can be co-edited live — mirrors COLLAB_FIELDS in
 * backend/utils/collab_fields.py (the server refuses any other room). Both
 * the full edit pages and the view pages' double-click editors join the same
 * room per (record, field), so they sync with each other.
 */
export const LIVE_FIELDS: Record<string, ReadonlySet<string>> = {
    finding: new Set(['description', 'impact', 'steps_to_reproduce', 'technical_details', 'mitigations', 'references']),
    testcase: new Set(['description', 'steps', 'expected_result', 'notes', 'actual_result']),
    asset: new Set(['description', 'notes']),
};

export const isLiveField = (resourceType?: string, field?: string): boolean =>
    !!resourceType && !!field && !!LIVE_FIELDS[resourceType]?.has(field);
