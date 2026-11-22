import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

/**
 * A calendar date ("YYYY-MM-DD", e.g. from <input type="date"> or a by-day
 * series) as local midnight. new Date("YYYY-MM-DD") is UTC midnight, which is
 * the previous day anywhere west of UTC. Other strings parse as new Date().
 */
export function parseDateOnly(dateStr: string): Date {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(dateStr);
}

/**
 * Parse a date string from the backend as UTC.
 * Backend timestamps are stored in UTC but may lack a Z suffix,
 * causing JS to interpret them as local time.
 */
export function parseUTCDate(dateStr: string): Date {
    // If it already has timezone info, parse as-is
    if (dateStr.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(dateStr)) {
        return new Date(dateStr);
    }
    // Otherwise append Z to force UTC interpretation
    return new Date(dateStr + 'Z');
}
