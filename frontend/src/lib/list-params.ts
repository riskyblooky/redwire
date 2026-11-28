/**
 * A list's view state (search, filters, sort, page) in the URL query
 * string, so back / forward, reload and a shared link keep it.
 *
 * A spec names each key and its kind. Values equal to their default are
 * left out of the URL; multi-value keys repeat (`?severity=HIGH&severity=LOW`);
 * an unparsable value falls back to the default. A ``prefix`` namespaces the
 * keys when several lists share a page (the engagement tabs).
 *
 * Pure functions here; the React hook is ``useListParams``.
 */

export type ParamKind =
    | { kind: 'string'; default?: string }
    | { kind: 'array'; default?: string[] }
    | { kind: 'int'; default: number; min?: number; max?: number }
    | { kind: 'enum'; values: readonly string[]; default: string };

export type ParamSpec = Record<string, ParamKind>;

type ValueOf<K extends ParamKind> =
    K extends { kind: 'array' } ? string[] :
    K extends { kind: 'int' } ? number :
    string;

export type ParamState<S extends ParamSpec> = { [P in keyof S]: ValueOf<S[P]> };

function defaultOf(k: ParamKind): string | string[] | number {
    switch (k.kind) {
        case 'array': return k.default ?? [];
        case 'int': return k.default;
        case 'enum': return k.default;
        default: return k.default ?? '';
    }
}

function same(a: unknown, b: unknown): boolean {
    if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => v === b[i]);
    return a === b;
}

export function readListParams<S extends ParamSpec>(search: URLSearchParams, spec: S, prefix = ''): ParamState<S> {
    const out: Record<string, unknown> = {};
    for (const [name, k] of Object.entries(spec)) {
        const key = prefix + name;
        if (k.kind === 'array') {
            const vals = search.getAll(key).filter(Boolean);
            out[name] = vals.length ? vals : defaultOf(k);
        } else if (k.kind === 'int') {
            const raw = search.get(key);
            const n = raw === null ? NaN : Number(raw);
            const ok = Number.isInteger(n) && (k.min === undefined || n >= k.min) && (k.max === undefined || n <= k.max);
            out[name] = ok ? n : k.default;
        } else if (k.kind === 'enum') {
            const raw = search.get(key);
            out[name] = raw !== null && k.values.includes(raw) ? raw : k.default;
        } else {
            out[name] = search.get(key) ?? defaultOf(k);
        }
    }
    return out as ParamState<S>;
}

/** A copy of ``search`` with this list's keys set from ``state``; other keys
 *  (another list's, ``tab``, ...) are kept as they are. */
export function writeListParams<S extends ParamSpec>(
    search: URLSearchParams, spec: S, state: Partial<ParamState<S>>, prefix = '',
): URLSearchParams {
    const next = new URLSearchParams(search);
    for (const [name, k] of Object.entries(spec)) {
        if (!(name in state)) continue;
        const key = prefix + name;
        const value = (state as Record<string, unknown>)[name];
        next.delete(key);
        if (value === undefined || value === null || same(value, defaultOf(k))) continue;
        if (Array.isArray(value)) value.filter(Boolean).forEach((v) => next.append(key, String(v)));
        else if (value !== '') next.set(key, String(value));
    }
    return next;
}

/** True when any key differs from its default (e.g. for "Clear filters"). */
export function hasNonDefault<S extends ParamSpec>(spec: S, state: ParamState<S>, keys: (keyof S)[]): boolean {
    return keys.some((name) => !same(state[name], defaultOf(spec[name as string])));
}

/** ``page`` (1-based) and ``pageSize`` as the backend's skip / limit. */
export function toSkipLimit(page: number, pageSize: number): { skip: number; limit: number } {
    return { skip: Math.max(0, (page - 1) * pageSize), limit: pageSize };
}
