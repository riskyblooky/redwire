/**
 * Shared react-grid-layout conversion for widget grids. Used by both the
 * per-user dashboard and the shared stats pages so their layout math can't
 * drift apart.
 */
import type { DashboardWidgetDef, LayoutItem } from '@/lib/hooks/use-dashboard-widgets';

/** Widget size → default grid span (6-col grid). */
export const SIZE_SPANS: Record<string, { col: number; row: number }> = {
    small: { col: 1, row: 1 },
    medium: { col: 2, row: 1 },
    large: { col: 2, row: 2 },
    wide: { col: 3, row: 1 },
    full: { col: 6, row: 1 },
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function layoutToRGL(items: LayoutItem[], widgets: DashboardWidgetDef[]): any[] {
    const widgetMap = new Map(widgets.map(w => [w.id, w]));
    return items.map((item, idx) => {
        const widget = widgetMap.get(item.widget_id);
        const defaults = SIZE_SPANS[widget?.size || 'medium'] || SIZE_SPANS.medium;
        return {
            i: item.widget_id,
            x: item.x ?? (idx % 6),
            y: item.y ?? Math.floor(idx / 3),
            w: item.w || defaults.col,
            h: item.h || defaults.row,
            minW: 1,
            maxW: 6,
            minH: 1,
            maxH: 4,
        };
    });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function rglToLayout(rglLayout: any[]): LayoutItem[] {
    return rglLayout.map(l => ({
        widget_id: l.i,
        x: l.x,
        y: l.y,
        w: l.w,
        h: l.h,
    }));
}
