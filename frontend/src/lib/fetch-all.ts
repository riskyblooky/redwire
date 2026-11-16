import api from './api';

/** The backend's per-request cap (`MAX_LIST_LIMIT`). */
export const MAX_PAGE_SIZE = 500;
/** Stop paging past this many rows; something is wrong before it matters. */
const MAX_ROWS = 50_000;

/**
 * Fetch every row of a `skip`/`limit` list endpoint, page by page.
 *
 * Hooks that feed pickers, charts and per-engagement tabs expect the whole
 * set. A single request silently stopped at the endpoint's default or cap
 * (25 engagements on the Planning chart, 100 assets in pickers, 500
 * findings or test cases), so the rest just wasn't there. The endpoints
 * order with an id tiebreaker, so pages don't overlap.
 *
 * `items` extracts the rows when the endpoint wraps them (e.g. `{items, total}`).
 */
export async function fetchAllPages<T>(
    url: string,
    params: Record<string, unknown> = {},
    items: (data: any) => T[] = (d) => d as T[],
    pageSize: number = MAX_PAGE_SIZE,
): Promise<T[]> {
    const rows: T[] = [];
    for (let skip = 0; ; skip += pageSize) {
        const { data } = await api.get(url, { params: { ...params, skip, limit: pageSize } });
        const page = items(data);
        rows.push(...page);
        if (page.length < pageSize) return rows;
        if (rows.length >= MAX_ROWS) {
            console.warn(`fetchAllPages(${url}): stopped at ${rows.length} rows`);
            return rows;
        }
    }
}
