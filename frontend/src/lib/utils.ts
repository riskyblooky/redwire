import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export function getAvatarUrl(path: string | null | undefined): string | undefined {
    if (!path) return undefined;
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    // Ensure no double slashes if path starts with slash
    const cleanPath = path.startsWith('/') ? path.substring(1) : path;
    return `${baseUrl}/${cleanPath}`;
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
