/**
 * Value dropdowns shared by the org and personal automation-rule editors.
 * Backend enum values are lowercase (see backend/routers/automations.py's
 * ConditionSchema + the router-side condition evaluator). Keep in sync
 * with those enums when adding fields — the personal editor also relies
 * on this map for its condition value dropdown.
 */
export const AUTOMATION_KNOWN_VALUES: Record<string, { label: string; value: string }[]> = {
    severity: [
        { label: 'Critical', value: 'critical' },
        { label: 'High', value: 'high' },
        { label: 'Medium', value: 'medium' },
        { label: 'Low', value: 'low' },
        { label: 'Info', value: 'info' },
    ],
    status: [
        { label: 'Open', value: 'open' },
        { label: 'In Review', value: 'in_review' },
        { label: 'Verified', value: 'verified' },
        { label: 'Remediated', value: 'remediated' },
        { label: 'Closed', value: 'closed' },
        { label: 'Pending', value: 'pending' },
        { label: 'Cleaned', value: 'cleaned' },
        { label: 'Skipped', value: 'skipped' },
    ],
    resource_type: [
        { label: 'Finding', value: 'finding' },
        { label: 'Engagement', value: 'engagement' },
        { label: 'Asset', value: 'asset' },
        { label: 'Test Case', value: 'testcase' },
        { label: 'Evidence', value: 'evidence' },
        { label: 'Note', value: 'note' },
        { label: 'Comment', value: 'comment' },
        { label: 'Vault', value: 'vault' },
        { label: 'Cleanup', value: 'cleanup_artifact' },
    ],
    asset_type: [
        { label: 'IP Address', value: 'ip_address' },
        { label: 'Domain', value: 'domain' },
        { label: 'URL', value: 'url' },
        { label: 'Application', value: 'application' },
        { label: 'Server', value: 'server' },
        { label: 'Network', value: 'network' },
        { label: 'Other', value: 'other' },
    ],
};
