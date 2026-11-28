import { describe, expect, it } from 'vitest';
import {
    canTransition, ENGAGEMENT_STATUSES, ENGAGEMENT_STATUS_BADGE, ENGAGEMENT_STATUS_BADGE_FALLBACK,
    ENGAGEMENT_STATUS_HEX, ENGAGEMENT_STATUS_LABELS, STATUS_PHASE_INDEX,
} from '@/lib/engagement-status';

const ALL = ['PROPOSED', 'SCOPING', 'PLANNING', 'IN_PROGRESS', 'REPORTING', 'COMPLETED', 'ON_HOLD'];
const STAGES = ['PROPOSED', 'SCOPING', 'PLANNING', 'IN_PROGRESS', 'REPORTING'];

// Transcription of backend/utils/engagement_status.py::_build(), which is
// the rule the backend enforces; canTransition must agree on every pair.
function backendAllowed(from: string, to: string): boolean {
    if (from === to) return true;
    const allowed = new Map<string, Set<string>>();
    STAGES.forEach((stage, i) => {
        const next = new Set(STAGES.slice(i + 1));
        if (i > 0) next.add(STAGES[i - 1]);
        next.add('ON_HOLD');
        allowed.set(stage, next);
    });
    allowed.get('REPORTING')!.add('COMPLETED');
    allowed.set('ON_HOLD', new Set(STAGES));
    allowed.set('COMPLETED', new Set());
    return allowed.get(from)!.has(to);
}

describe('canTransition', () => {
    it.each(ALL.flatMap(from => ALL.map(to => [from, to] as const)))(
        '%s → %s matches the backend rule',
        (from, to) => {
            expect(canTransition(from, to)).toBe(backendAllowed(from, to));
        },
    );

    it('spot checks', () => {
        expect(canTransition('PROPOSED', 'REPORTING')).toBe(true);   // forward any distance
        expect(canTransition('PLANNING', 'SCOPING')).toBe(true);     // back one
        expect(canTransition('IN_PROGRESS', 'SCOPING')).toBe(false); // back two
        expect(canTransition('IN_PROGRESS', 'COMPLETED')).toBe(false);
        expect(canTransition('REPORTING', 'COMPLETED')).toBe(true);
        expect(canTransition('COMPLETED', 'REPORTING')).toBe(false); // reopen is admin-only
        expect(canTransition('ON_HOLD', 'COMPLETED')).toBe(false);
        expect(canTransition('ON_HOLD', 'PROPOSED')).toBe(true);
    });

    it('leaves a missing or unknown current status unrestricted', () => {
        expect(canTransition(null, 'COMPLETED')).toBe(true);
        expect(canTransition(undefined, 'COMPLETED')).toBe(true);
        expect(canTransition('', 'COMPLETED')).toBe(true);
        expect(canTransition('LEGACY_VALUE', 'COMPLETED')).toBe(true);
    });

    it('allows staying on the current status, even COMPLETED', () => {
        for (const s of ALL) expect(canTransition(s, s)).toBe(true);
    });
});

describe('status tables', () => {
    it('lists every status once, in lifecycle order, with a label', () => {
        expect(ENGAGEMENT_STATUSES.map(s => s.value)).toEqual(ALL);
        expect(ENGAGEMENT_STATUS_LABELS.IN_PROGRESS).toBe('In Progress');
        expect(ENGAGEMENT_STATUS_LABELS.ON_HOLD).toBe('On Hold');
        expect(Object.keys(ENGAGEMENT_STATUS_LABELS).sort()).toEqual([...ALL].sort());
    });

    it('gives every status a badge, a chart colour and a phase index', () => {
        for (const s of ALL) {
            expect(ENGAGEMENT_STATUS_BADGE[s]).toMatch(/^bg-\w+-500\/10 text-\w+-400 border-\w+-500\/20$/);
            expect(ENGAGEMENT_STATUS_HEX[s]).toMatch(/^#[0-9a-f]{6}$/);
            expect(STATUS_PHASE_INDEX).toHaveProperty(s);
        }
        expect(ENGAGEMENT_STATUS_BADGE_FALLBACK).toBe(ENGAGEMENT_STATUS_BADGE.ON_HOLD);
    });

    it('numbers phases in lifecycle order, with PROPOSED and ON_HOLD outside it', () => {
        expect(['SCOPING', 'PLANNING', 'IN_PROGRESS', 'REPORTING', 'COMPLETED'].map(s => STATUS_PHASE_INDEX[s]))
            .toEqual([0, 1, 2, 3, 4]);
        expect(STATUS_PHASE_INDEX.PROPOSED).toBe(-1);
        expect(STATUS_PHASE_INDEX.ON_HOLD).toBe(-1);
    });
});
