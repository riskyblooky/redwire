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

/** Status badge classes — the one engagement-status palette (teal, cyan,
 *  amber, purple, blue, green, slate in lifecycle order). The calendar
 *  views use the same hues in their own tile shapes. */
export const ENGAGEMENT_STATUS_BADGE: Record<string, string> = {
    PROPOSED:    'bg-teal-500/10 text-teal-400 border-teal-500/20',
    SCOPING:     'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    PLANNING:    'bg-amber-500/10 text-amber-400 border-amber-500/20',
    IN_PROGRESS: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    REPORTING:   'bg-blue-500/10 text-blue-400 border-blue-500/20',
    COMPLETED:   'bg-green-500/10 text-green-400 border-green-500/20',
    ON_HOLD:     'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

export const ENGAGEMENT_STATUS_BADGE_FALLBACK = ENGAGEMENT_STATUS_BADGE.ON_HOLD;

/** The same palette as hex (Tailwind 500 shades), for charts. */
export const ENGAGEMENT_STATUS_HEX: Record<string, string> = {
    PROPOSED: '#14b8a6', SCOPING: '#06b6d4', PLANNING: '#f59e0b', IN_PROGRESS: '#a855f7',
    REPORTING: '#3b82f6', COMPLETED: '#22c55e', ON_HOLD: '#64748b',
};
