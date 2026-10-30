/**
 * Canonical severity palette — the one place severity colors are defined.
 *
 * Theme: Critical=red-500, High=orange-500, Medium=yellow-500, Low=blue-400,
 * Info=slate-400. The hex values mirror backend scoring/severity.py
 * SEVERITY_COLORS. Keys are the uppercase Severity enum values.
 */

/** Outlined badge classes. Order is bg, text, border — some callers pick the
 *  text class out with `.split(' ')[1]`. */
export const SEVERITY_BADGE: Record<string, string> = {
    CRITICAL: 'bg-red-500/15 text-red-400 border-red-500/30',
    HIGH: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    MEDIUM: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    LOW: 'bg-blue-400/15 text-blue-400 border-blue-400/30',
    INFO: 'bg-slate-400/15 text-slate-400 border-slate-400/30',
};

/** Solid fill classes (accent bars, dots). */
export const SEVERITY_SOLID: Record<string, string> = {
    CRITICAL: 'bg-red-500',
    HIGH: 'bg-orange-500',
    MEDIUM: 'bg-yellow-500',
    LOW: 'bg-blue-400',
    INFO: 'bg-slate-400',
};

/** Hex colors for charts and inline styles. */
export const SEVERITY_HEX: Record<string, string> = {
    CRITICAL: '#ef4444',
    HIGH: '#f97316',
    MEDIUM: '#eab308',
    LOW: '#60a5fa',
    INFO: '#94a3b8',
};

/** Case-insensitive hex lookup ("critical", "Critical", "CRITICAL");
 *  undefined for unknown values so callers keep their own fallback. */
export function severityHex(severity?: string | null): string | undefined {
    return severity ? SEVERITY_HEX[severity.toUpperCase()] : undefined;
}
