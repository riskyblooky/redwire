import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UserSettingsState {
    preferredEditor: 'tiptap';
    setPreferredEditor: (editor: 'tiptap') => void;
}

export const useUserSettingsStore = create<UserSettingsState>()(
    persist(
        (set) => ({
            preferredEditor: 'tiptap',
            setPreferredEditor: (editor) => set({ preferredEditor: editor }),
        }),
        {
            name: 'user-settings',
        }
    )
);
