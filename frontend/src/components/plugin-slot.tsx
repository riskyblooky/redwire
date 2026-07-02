'use client';

/**
 * Plugin extension slot.
 *
 * Core pages render a ``<PluginSlot slot="engagement.tabs" props={...} />``
 * anywhere they want plugin-registered content. Two things drive it:
 *
 *   1. Backend ``GET /plugins/extensions/{slot}`` returns metadata for
 *      every plugin entry registered against the slot, filtered by the
 *      caller's global permissions (see PluginRegistry.get_extensions).
 *      Payload shape per entry:
 *        { component, label?, plugin_slug, plugin_id, slot, ... }
 *
 *   2. Frontend registry ``_extensions.generated.tsx`` (built by
 *      ``sync-plugin-frontends.mjs``) maps ``<slug>:<component>`` to the
 *      component's default export.
 *
 * The render decision is: for every backend entry, look up the component
 * in the registry — skip with a console warning if missing. That way a
 * plugin whose manifest advertises an extension but forgot to ship the
 * component file fails loudly.
 *
 * Backend RBAC is the source of truth for visibility. The frontend
 * never guesses — if the entry isn't in the API response, it doesn't
 * render.
 */
import { ReactNode, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import { PLUGIN_EXTENSION_COMPONENTS } from '@/app/plugins/_extensions.generated';

export interface PluginExtension {
    component: string;
    label?: string;
    plugin_slug: string;
    plugin_id: string;
    slot: string;
    // Plugin authors can freely add extra fields; forward-compat.
    [key: string]: any;
}

interface PluginSlotProps<TProps extends Record<string, any> = Record<string, any>> {
    slot: string;
    /** Props forwarded to every rendered extension. Kept typed as ``any``
     *  because different slots pass different context; each plugin's
     *  component knows its own shape. */
    props?: TProps;
    /** Optional render prop for wrapping every extension — used by the
     *  engagement-detail tabs render to wrap each entry in a
     *  ``<TabsTrigger>``. Defaults to a passthrough. */
    renderWrapper?: (entry: PluginExtension, node: ReactNode) => ReactNode;
    /** Fallback when the API errors or returns nothing. Default: null. */
    fallback?: ReactNode;
}

export function PluginSlot<TProps extends Record<string, any>>({
    slot,
    props,
    renderWrapper,
    fallback = null,
}: PluginSlotProps<TProps>) {
    const { data: entries, isError } = useQuery({
        // Slot in the key so different slots are cached independently;
        // the same slot re-uses the fetch across many render sites.
        queryKey: ['plugin-extensions', slot],
        queryFn: async () => {
            const { data } = await api.get<PluginExtension[]>(
                `/plugins/extensions/${encodeURIComponent(slot)}`,
            );
            return data;
        },
        // Extensions don't change per user action, but they DO change when
        // an admin toggles a plugin — the plugin management page can
        // invalidate this key to refresh live.
        staleTime: 60_000,
    });

    const rendered = useMemo(() => {
        if (!entries) return [];
        return entries.map((entry) => {
            const key = `${entry.plugin_slug}:${entry.component}`;
            const Component = PLUGIN_EXTENSION_COMPONENTS[key];
            if (!Component) {
                if (typeof console !== 'undefined') {
                    console.warn(
                        `[PluginSlot] no component registered for ${key} `
                        + `(slot=${slot}). The manifest advertises this extension `
                        + `but the file at plugins/${entry.plugin_slug}/frontend/`
                        + `extensions/${entry.component}.tsx wasn't found at build.`
                    );
                }
                return null;
            }
            const node = <Component {...(props ?? {})} entry={entry} />;
            const wrapped = renderWrapper ? renderWrapper(entry, node) : node;
            return <div key={key}>{wrapped}</div>;
        });
    }, [entries, props, renderWrapper, slot]);

    if (isError) return <>{fallback}</>;
    if (!rendered.length) return <>{fallback}</>;
    return <>{rendered}</>;
}
