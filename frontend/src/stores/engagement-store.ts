import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface EngagementContextState {
    selectedEngagementId: string | 'global' | null;
    setSelectedEngagement: (engagementId: string | 'global' | null) => void;
    clearSelectedEngagement: () => void;
}

export const useEngagementContext = create<EngagementContextState>()(
    persist(
        (set) => ({
            selectedEngagementId: null,
            // 'new' is the create-form route segment, never an engagement.
            setSelectedEngagement: (engagementId) => set({ selectedEngagementId: engagementId === 'new' ? null : engagementId }),
            clearSelectedEngagement: () => set({ selectedEngagementId: null }),
        }),
        {
            name: 'engagement-context',
            // Drop a 'new' persisted by older builds.
            merge: (persisted, current) => {
                const p = (persisted ?? {}) as Partial<EngagementContextState>;
                return { ...current, ...p, selectedEngagementId: p.selectedEngagementId === 'new' ? null : (p.selectedEngagementId ?? null) };
            },
        }
    )
);
