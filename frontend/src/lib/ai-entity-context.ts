/**
 * Builders that turn a record (finding / testcase / engagement / asset) into
 * the small `entityContext` bag consumed by the in-editor AI assistant. Each
 * returns human-friendly label → value pairs; empty/blank values are dropped
 * so the AI prompt only carries facts that are actually set. Keep these lean —
 * the backend caps the block, and the goal is grounding, not a full dump.
 *
 * These accept loose shapes on purpose: the same builder is used across the
 * new / edit (formData) and detail (API record) pages, whose field names line
 * up but whose TS types differ.
 */

type Ctx = Record<string, string | number | null | undefined>;

/** Drop null/undefined/blank values so the AI prompt stays tight. */
function compact(ctx: Ctx): Ctx {
    const out: Ctx = {};
    for (const [k, v] of Object.entries(ctx)) {
        if (v === null || v === undefined) continue;
        if (typeof v === 'string' && v.trim() === '') continue;
        out[k] = v;
    }
    return out;
}

/** Format "8.1" + "CVSS:3.1/…" into a single readable CVSS string. */
function cvss(score?: number | string | null, vector?: string | null): string | undefined {
    const s = score !== null && score !== undefined && `${score}`.trim() !== '' ? `${score}` : '';
    const v = vector && vector.trim() ? vector.trim() : '';
    if (s && v) return `${s} (${v})`;
    return s || v || undefined;
}

export function buildFindingContext(f: any): Ctx {
    if (!f) return {};
    return compact({
        Title: f.title,
        Severity: f.severity,
        CVSS: cvss(f.cvss_score, f.cvss_vector),
        Status: f.status,
        Category: f.category,
    });
}

export function buildTestcaseContext(t: any): Ctx {
    if (!t) return {};
    return compact({
        Title: t.title,
        Status: t.status,
        Category: t.category,
        Priority: t.priority,
    });
}

export function buildEngagementContext(e: any): Ctx {
    if (!e) return {};
    return compact({
        Name: e.name,
        Type: e.engagement_type,
        Status: e.status,
        Client: e.client_name,
    });
}

export function buildAssetContext(a: any): Ctx {
    if (!a) return {};
    return compact({
        Name: a.name,
        Type: a.asset_type,
        Identifier: a.identifier,
        Status: a.status,
    });
}
