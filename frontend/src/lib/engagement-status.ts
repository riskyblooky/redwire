/**
 * Engagement status transitions a non-admin may make — mirrors
 * backend/utils/engagement_status.py (the backend enforces; this only greys
 * out options). Admins and team leads may make any transition.
 */
/** Engagement statuses in lifecycle order (backend EngagementStatus), with
 *  their display labels. The one list every status select and label uses. */
export const ENGAGEMENT_STATUSES: { value: string; label: string }[] = [
    { value: 'PROPOSED',    label: 'Proposed'    },
    { value: 'SCOPING',     label: 'Scoping'     },
    { value: 'PLANNING',    label: 'Planning'    },
    { value: 'IN_PROGRESS', label: 'In Progress' },
    { value: 'REPORTING',   label: 'Reporting'   },
    { value: 'COMPLETED',   label: 'Completed'   },
    { value: 'ON_HOLD',     label: 'On Hold'     },
];

export const ENGAGEMENT_STATUS_LABELS: Record<string, string> =
    Object.fromEntries(ENGAGEMENT_STATUSES.map(s => [s.value, s.label]));

// The forward sequence; COMPLETED and ON_HOLD are handled separately.
const STAGES = ENGAGEMENT_STATUSES.map(s => s.value).filter(v => v !== 'COMPLETED' && v !== 'ON_HOLD');

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

/** Position of each phase / status in the engagement lifecycle, for phase
 *  health (a phase is done once the status is past it). PROPOSED and
 *  ON_HOLD are outside the sequence. Same order as STAGES and the
 *  backend's EngagementPhase.DEFAULT_PHASES. */
export const STATUS_PHASE_INDEX: Record<string, number> = {
    PROPOSED: -1, SCOPING: 0, PLANNING: 1, IN_PROGRESS: 2, REPORTING: 3, COMPLETED: 4, ON_HOLD: -1,
};
