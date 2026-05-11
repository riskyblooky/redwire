/**
 * DashboardGrid — Dynamically loaded wrapper around react-grid-layout
 *
 * react-grid-layout v1.x CJS exports don't survive Next.js webpack's ESM
 * resolution. This component dynamically creates the grid component on mount
 * using a state-based pattern that bypasses static import analysis.
 */
'use client';

import React, { useCallback, useEffect, useState } from 'react';

interface DashboardGridProps {
    layout: any[];
    isEditing: boolean;
    onLayoutChange: (layout: any[]) => void;
    children: React.ReactNode;
}

export default function DashboardGrid({ layout, isEditing, onLayoutChange, children }: DashboardGridProps) {
    const [GridComponent, setGridComponent] = useState<any>(null);

    useEffect(() => {
        // Dynamic import at runtime — completely bypasses webpack's static ESM analysis
        import('react-grid-layout').then((mod) => {
            // v1.x: default export is ReactGridLayout, named exports include Responsive + WidthProvider
            // v2.x: different export structure
            // Try named first, then default.WidthProvider, then module.WidthProvider
            const RGL = mod.default || mod;
            const Responsive = mod.Responsive || RGL.Responsive;
            const WidthProvider = mod.WidthProvider || RGL.WidthProvider;

            if (Responsive && WidthProvider) {
                setGridComponent(() => WidthProvider(Responsive));
            } else if (RGL && typeof RGL === 'function') {
                // Fallback: just use the default export directly
                const WP = mod.WidthProvider || RGL.WidthProvider;
                if (WP) {
                    setGridComponent(() => WP(RGL));
                }
            }
        });
    }, []);

    const handleChange = useCallback((newLayout: any[]) => {
        if (!isEditing) return;
        onLayoutChange(newLayout);
    }, [isEditing, onLayoutChange]);

    if (!GridComponent) {
        return (
            <div className="grid grid-cols-6 gap-3 auto-rows-[130px]">
                {children}
            </div>
        );
    }

    const ResponsiveGridLayout = GridComponent;

    return (
        <ResponsiveGridLayout
            className="dashboard-grid"
            layouts={{ lg: layout, md: layout, sm: layout }}
            breakpoints={{ lg: 1200, md: 996, sm: 768 }}
            cols={{ lg: 6, md: 4, sm: 2 }}
            rowHeight={130}
            margin={[12, 12]}
            containerPadding={[0, 0]}
            isDraggable={isEditing}
            isResizable={isEditing}
            compactType="vertical"
            onLayoutChange={handleChange}
            draggableHandle=".rgl-drag-handle"
            resizeHandles={['se']}
            useCSSTransforms={true}
        >
            {children}
        </ResponsiveGridLayout>
    );
}
