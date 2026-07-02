/**
 * Icon lookup for plugin nav items.
 *
 * Plugin manifests declare an ``icon`` name (a string). We resolve it to a
 * lucide-react component here. Statically importing the icons keeps
 * tree-shaking predictable — a dynamic ``import * as icons from
 * 'lucide-react'`` would pull the entire library into whatever bundle
 * touches it.
 *
 * If a plugin author wants an icon that isn't in this map, either
 *   (a) add it here (one line), or
 *   (b) omit ``icon:`` and get the default ``Plug`` glyph.
 *
 * The set is chosen to cover the integration types we've seen in the
 * wild: SaaS APIs, data stores, ticketing, monitoring, security,
 * comms, workflow. Keep additions alphabetical.
 */
import type { LucideIcon } from 'lucide-react';
import {
    Activity,
    AlertTriangle,
    BarChart,
    Bell,
    Bot,
    Bug,
    Cloud,
    Code,
    Compass,
    CreditCard,
    Database,
    FileText,
    Filter,
    Flag,
    Folder,
    Gauge,
    Globe,
    HardDrive,
    Key,
    Layers,
    Lock,
    Mail,
    Map,
    Network,
    Package,
    Plug,
    Radar,
    Rocket,
    Search,
    Server,
    Share2,
    Shield,
    Slack,
    Star,
    Table,
    Ticket,
    Users,
    Webhook,
    Workflow,
    Zap,
} from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
    Activity,
    AlertTriangle,
    BarChart,
    Bell,
    Bot,
    Bug,
    Cloud,
    Code,
    Compass,
    CreditCard,
    Database,
    FileText,
    Filter,
    Flag,
    Folder,
    Gauge,
    Globe,
    HardDrive,
    Key,
    Layers,
    Lock,
    Mail,
    Map,
    Network,
    Package,
    Plug,
    Radar,
    Rocket,
    Search,
    Server,
    Share2,
    Shield,
    Slack,
    Star,
    Table,
    Ticket,
    Users,
    Webhook,
    Workflow,
    Zap,
};

/**
 * Resolve a plugin manifest's ``icon`` value to a component.
 * Returns ``Plug`` when the name is missing or not in the whitelist.
 */
export function getPluginIcon(name?: string | null): LucideIcon {
    if (!name) return Plug;
    return ICONS[name] ?? Plug;
}

/** Public list of supported icon names — for documentation / admin UI. */
export const PLUGIN_ICON_NAMES = Object.keys(ICONS);
