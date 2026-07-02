'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode, useEffect } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { AuthGuard } from '@/components/auth/auth-guard';
import { AiChatbot } from '@/components/ui/ai-chatbot';

const ALLOWED_ACCENTS = new Set(['purple', 'crimson', 'blue', 'emerald', 'amber', 'custom']);
const ALLOWED_PALETTES = new Set(['aurora', 'operator', 'half-dark', 'light']);

// Convert "#a855f7" to "263 89% 63%" (HSL) so it can be assigned to
// the --primary CSS variable, which is consumed as `hsl(var(--primary))`.
function hexToHslTriplet(hex: string): string | null {
    const m = /^#([0-9a-fA-F]{6})$/.exec(hex);
    if (!m) return null;
    const r = parseInt(m[1].slice(0, 2), 16) / 255;
    const g = parseInt(m[1].slice(2, 4), 16) / 255;
    const b = parseInt(m[1].slice(4, 6), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let h = 0, s = 0;
    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = ((g - b) / d + (g < b ? 6 : 0)); break;
            case g: h = ((b - r) / d + 2); break;
            case b: h = ((r - g) / d + 4); break;
        }
        h *= 60;
    }
    return `${Math.round(h)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

function ThemeApplier() {
    const accent = useAuthStore(s => s.user?.theme_preference);
    const palette = useAuthStore(s => s.user?.theme_palette);
    const customHex = useAuthStore(s => s.user?.theme_accent_custom);
    useEffect(() => {
        const root = document.documentElement;
        // Defaults: accent=purple, palette=aurora — only set attributes when
        // overrides are selected. CSS keys off data-accent and data-palette.
        if (accent && ALLOWED_ACCENTS.has(accent) && accent !== 'purple') {
            root.setAttribute('data-accent', accent);
        } else {
            root.removeAttribute('data-accent');
        }
        if (palette && ALLOWED_PALETTES.has(palette) && palette !== 'aurora') {
            root.setAttribute('data-palette', palette);
        } else {
            root.removeAttribute('data-palette');
        }

        // Custom accent: when accent === 'custom' and a hex is set, write
        // an inline --primary / --ring on <html> so it cascades to all
        // bg-primary / text-primary / ring-primary utilities.
        if (accent === 'custom' && customHex) {
            const hsl = hexToHslTriplet(customHex);
            if (hsl) {
                root.style.setProperty('--primary', hsl);
                root.style.setProperty('--primary-soft', hsl);
                root.style.setProperty('--ring', hsl);
            }
        } else {
            root.style.removeProperty('--primary');
            root.style.removeProperty('--primary-soft');
            root.style.removeProperty('--ring');
        }
    }, [accent, palette, customHex]);
    return null;
}

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 60 * 1000, // 1 minute
            refetchOnWindowFocus: false,
        },
    },
});

import { Toaster } from 'sonner';

export function Providers({ children }: { children: ReactNode }) {
    return (
        <QueryClientProvider client={queryClient}>
            <ThemeApplier />
            <AuthGuard>
                {children}
                <AiChatbot />
            </AuthGuard>
            <Toaster
                richColors
                position="top-right"
                theme="dark"
                // Push below the 64px (h-16) dashboard header so toasts
                // don't overlap the search / notifications menus that
                // open from the top bar.
                offset="80px"
                toastOptions={{
                    style: {
                        background: 'rgb(15 23 42)',       // slate-900
                        border: '1px solid rgb(30 41 59)', // slate-800
                        color: 'rgb(226 232 240)',         // slate-200
                    },
                    classNames: {
                        success: 'border-green-800/50! bg-green-950/80!',
                        error: 'border-red-800/50! bg-red-950/80!',
                        warning: 'border-amber-800/50! bg-amber-950/80!',
                        info: 'border-blue-800/50! bg-blue-950/80!',
                    },
                }}
            />
        </QueryClientProvider>
    );
}
