import api from './api';

/** One server page of a list and the total matching the filters. */
export interface Page<T> {
    rows: T[];
    total: number;
}

/** Repeated keys for arrays (`severity=HIGH&severity=LOW`), which is what
 *  FastAPI's ``List[...]`` query parameters read; axios's default
 *  (`severity[]=`) isn't. Empty strings and empty arrays are left out. */
export function serializeListQuery(params: Record<string, unknown>): string {
    const out = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value === undefined || value === null || value === '') continue;
        if (Array.isArray(value)) value.filter((v) => v !== '' && v != null).forEach((v) => out.append(key, String(v)));
        else out.set(key, String(value));
    }
    return out.toString();
}

/** GET a paged list. The total comes from ``X-Total-Count``, or from an
 *  ``{items, total}`` body for the endpoints that return one. */
export async function fetchPage<T>(url: string, params: Record<string, unknown>): Promise<Page<T>> {
    const res = await api.get(url, { params, paramsSerializer: { serialize: serializeListQuery } });
    const data = res.data;
    if (Array.isArray(data)) {
        const header = Number(res.headers['x-total-count']);
        return { rows: data as T[], total: Number.isFinite(header) ? header : data.length };
    }
    return { rows: (data?.items ?? []) as T[], total: Number(data?.total ?? data?.items?.length ?? 0) };
}
