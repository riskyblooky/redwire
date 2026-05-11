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
            setSelectedEngagement: (engagementId) => set({ selectedEngagementId: engagementId }),
            clearSelectedEngagement: () => set({ selectedEngagementId: null }),
        }),
        {
            name: 'engagement-context',
        }
    )
);
