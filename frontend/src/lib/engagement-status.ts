/**
 * Engagement status transitions a non-admin may make — mirrors
 * backend/utils/engagement_status.py (the backend enforces; this only greys
 * out options). Admins and team leads may make any transition.
 */
const STAGES = ['PROPOSED', 'SCOPING', 'PLANNING', 'IN_PROGRESS', 'REPORTING'];

export function canTransition(from: string | null | undefined, to: string): boolean {
    if (!from || from === to) return true;
    if (from === 'COMPLETED') return false;
    if (from === 'ON_HOLD') return STAGES.includes(to);
    const i = STAGES.indexOf(from);
    if (i < 0) return true;
    if (to === 'ON_HOLD') return true;
    if (to === 'COMPLETED') return from === 'REPORTING';
    const j = STAGES.indexOf(to);
    return j > i || j === i - 1;
}
