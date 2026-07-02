/**
 * ServiceNow CMDB tab on the engagement detail page.
 *
 * Rendered when the plugin manifest registers this component against the
 * ``engagement.tabs`` slot. Props are forwarded from PluginSlot:
 *   * engagementId — the current engagement's id
 *   * entry        — the plugin manifest entry itself (label, etc.)
 *
 * This is a stub demonstrating the extension point works end-to-end.
 * Real plugin extensions would fetch CMDB data for the engagement's
 * assets and render whatever the operator finds useful.
 */
'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface CmdbTabProps {
    engagementId: string;
    entry: { label?: string; plugin_slug: string };
}

export default function CmdbTab({ engagementId, entry }: CmdbTabProps) {
    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader>
                <CardTitle className="text-white">{entry.label ?? 'ServiceNow CMDB'}</CardTitle>
            </CardHeader>
            <CardContent className="text-slate-300 text-sm space-y-2">
                <p>
                    Rendered by the <code className="text-emerald-400">servicenow_cmdb</code>{' '}
                    plugin via the <code className="text-emerald-400">engagement.tabs</code> slot.
                </p>
                <p>
                    Engagement id: <code className="text-slate-400">{engagementId}</code>
                </p>
                <p className="text-slate-500">
                    A real implementation would fetch CI matches for this engagement's assets
                    from the ServiceNow API endpoints defined in the plugin's router.
                </p>
            </CardContent>
        </Card>
    );
}
