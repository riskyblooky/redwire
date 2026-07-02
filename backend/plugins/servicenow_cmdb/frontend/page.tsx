/**
 * ServiceNow CMDB — plugin landing page.
 *
 * Synced from backend/plugins/servicenow_cmdb/frontend/ into
 * frontend/src/app/plugins/servicenow-cmdb/ at build time by
 * frontend/scripts/sync-plugin-frontends.mjs. Edit HERE, not in the
 * synced copy (which is overwritten on every next dev / next build).
 */
export default function ServicenowCmdbPage() {
    return (
        <div className="p-6">
            <h1 className="text-2xl font-semibold text-white">ServiceNow CMDB</h1>
            <p className="text-slate-400 mt-2">
                Plugin frontend served from
                <code className="ml-1 text-emerald-400">
                    backend/plugins/servicenow_cmdb/frontend/page.tsx
                </code>
            </p>
        </div>
    );
}
