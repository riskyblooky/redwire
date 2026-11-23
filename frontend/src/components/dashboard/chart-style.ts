/**
 * Recharts styling shared by the dashboard widgets and the widget builder's
 * preview (which had its own hex-coded copies).
 */

/** Series palette, in assignment order. */
export const ACCENT_COLORS = ['#818cf8', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#ef4444', '#ec4899', '#8b5cf6', '#14b8a6'];

/** Tooltip props on theme tokens so the popover matches the rest of the UI. */
export const TOOLTIP_STYLE = {
    contentStyle: {
        backgroundColor: 'hsl(var(--popover))',
        border: '1px solid hsl(var(--border))',
        borderRadius: '8px',
        color: 'hsl(var(--popover-foreground))',
        boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
    },
    itemStyle: { color: 'hsl(var(--popover-foreground))' },
    labelStyle: { color: 'hsl(var(--muted-foreground))' },
    wrapperStyle: { zIndex: 50, outline: 'none' },
    allowEscapeViewBox: { x: false, y: false } as { x: boolean; y: boolean },
};
