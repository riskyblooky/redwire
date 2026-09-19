import type { ResourceType } from '@/lib/hooks/use-discussions';

/** Human labels for the annotatable text fields, per resource type. */
export const FINDING_FIELD_LABELS: Record<string, string> = {
    description: 'Executive Summary',
    impact: 'Potential Impact',
    steps_to_reproduce: 'Steps to Reproduce',
    technical_details: 'Technical Details',
    mitigations: 'Mitigation & Remediation',
    references: 'External References',
};

export const TESTCASE_FIELD_LABELS: Record<string, string> = {
    description: 'Description',
    steps: 'Execution Steps',
    expected_result: 'Expected Result',
    notes: 'Notes',
};

export function fieldLabel(resourceType: ResourceType, field: string): string {
    const map = resourceType === 'testcase' ? TESTCASE_FIELD_LABELS : FINDING_FIELD_LABELS;
    return map[field] || field;
}

/**
 * Title for a new anchored thread: the field label plus a rolling number, e.g.
 * "Steps to Reproduce Review #3". The number is one past the highest "#N" already
 * used among the given field's threads, so it keeps climbing and never collides
 * with a live thread.
 */
export function nextThreadTitle(resourceType: ResourceType, field: string, existingTitles: string[]): string {
    let max = 0;
    for (const title of existingTitles) {
        const m = /#(\d+)\s*$/.exec(title || '');
        if (m) max = Math.max(max, parseInt(m[1], 10));
    }
    return `${fieldLabel(resourceType, field)} Review #${max + 1}`;
}
