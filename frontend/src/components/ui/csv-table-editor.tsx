'use client';

/**
 * CsvTableEditor — inline spreadsheet-style view/edit for CSV attachments.
 * Renders in place of the file preview (no modal): an editable grid of cells
 * (Excel-like row numbers + column letters) with add/delete row & column, and
 * Save/Cancel controls. Saves back over the same evidence via `onSave(blob)`.
 * RFC 4180 parse/serialize is inline — no new dependencies.
 */
import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Loader2, Save, X, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';

export function isCsv(mimeType?: string | null, filename?: string | null): boolean {
    const ext = (filename?.split('.').pop() || '').toLowerCase();
    if (ext === 'csv' || ext === 'tsv') return true;
    const mt = (mimeType || '').toLowerCase();
    return mt === 'text/csv' || mt === 'application/csv' || mt === 'text/tab-separated-values';
}

/** RFC 4180 parse: handles quoted fields with embedded commas, newlines and
 *  doubled-quote ("") escapes. Returns a ragged array of rows. */
export function parseCsv(text: string): string[][] {
    const rows: string[][] = [];
    let row: string[] = [];
    let field = '';
    let inQuotes = false;
    let i = 0;
    const pushField = () => { row.push(field); field = ''; };
    const pushRow = () => { rows.push(row); row = []; };
    while (i < text.length) {
        const c = text[i];
        if (inQuotes) {
            if (c === '"') {
                if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
                inQuotes = false; i++; continue;
            }
            field += c; i++; continue;
        }
        if (c === '"') { inQuotes = true; i++; continue; }
        if (c === ',') { pushField(); i++; continue; }
        if (c === '\r') { i++; continue; }        // fold CR; LF ends the row
        if (c === '\n') { pushField(); pushRow(); i++; continue; }
        field += c; i++;
    }
    if (field !== '' || row.length > 0) { pushField(); pushRow(); }
    return rows;
}

export function toCsv(rows: string[][]): string {
    return rows
        .map((r) => r.map((cell) => {
            const s = cell ?? '';
            return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        }).join(','))
        .join('\r\n');
}

/** 0 → A, 25 → Z, 26 → AA … (spreadsheet column labels). */
function colLabel(n: number): string {
    let s = '';
    n += 1;
    while (n > 0) {
        const r = (n - 1) % 26;
        s = String.fromCharCode(65 + r) + s;
        n = Math.floor((n - 1) / 26);
    }
    return s;
}

/** Pad every row to the same width so the grid is rectangular. */
function normalize(rows: string[][]): string[][] {
    const cols = Math.max(1, ...rows.map((r) => r.length));
    return (rows.length ? rows : [[]]).map((r) => {
        const copy = r.slice();
        while (copy.length < cols) copy.push('');
        return copy;
    });
}

interface CsvTableEditorProps {
    fileUrl: string;
    mimeType?: string | null;
    onSave: (blob: Blob) => Promise<void>;
    onCancel: () => void;
}

export default function CsvTableEditor({ fileUrl, mimeType, onSave, onCancel }: CsvTableEditorProps) {
    const [rows, setRows] = useState<string[][]>([['']]);
    const [baseline, setBaseline] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!fileUrl) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        fetch(fileUrl)
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text(); })
            .then((text) => {
                if (cancelled) return;
                const parsed = normalize(parseCsv(text));
                setRows(parsed);
                setBaseline(toCsv(parsed));
                setLoading(false);
            })
            .catch(() => { if (!cancelled) { setError('Failed to load the file for editing.'); setLoading(false); } });
        return () => { cancelled = true; };
    }, [fileUrl]);

    const colCount = rows[0]?.length || 1;
    const currentCsv = useMemo(() => toCsv(rows), [rows]);
    const isDirty = !loading && currentCsv !== baseline;

    const setCell = (r: number, c: number, v: string) => {
        setRows((prev) => prev.map((row, ri) => ri === r ? row.map((cell, ci) => ci === c ? v : cell) : row));
    };
    const addRow = () => setRows((prev) => [...prev, Array(prev[0]?.length || 1).fill('')]);
    const addCol = () => setRows((prev) => prev.map((row) => [...row, '']));
    const deleteRow = (r: number) => setRows((prev) => prev.length <= 1 ? prev : prev.filter((_, ri) => ri !== r));
    const deleteCol = (c: number) => setRows((prev) => (prev[0]?.length || 0) <= 1 ? prev : prev.map((row) => row.filter((_, ci) => ci !== c)));

    const handleSave = async () => {
        setSaving(true);
        try {
            const blob = new Blob([currentCsv], { type: mimeType || 'text/csv' });
            await onSave(blob);
            setBaseline(currentCsv);
        } catch (e) {
            toast.error(apiErrorMessage(e, 'Failed to save the file'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="flex h-full w-full flex-col self-stretch">
            {loading ? (
                <div className="flex flex-1 items-center justify-center text-slate-500"><Loader2 className="h-6 w-6 animate-spin" /></div>
            ) : error ? (
                <div className="flex flex-1 items-center justify-center text-slate-400 text-sm">{error}</div>
            ) : (
                <>
                    <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2">
                        <Button type="button" variant="outline" size="sm" onClick={addRow} className="h-8 border-slate-700 text-slate-300 hover:text-white">
                            <Plus className="h-3.5 w-3.5 mr-1.5" /> Row
                        </Button>
                        <Button type="button" variant="outline" size="sm" onClick={addCol} className="h-8 border-slate-700 text-slate-300 hover:text-white">
                            <Plus className="h-3.5 w-3.5 mr-1.5" /> Column
                        </Button>
                        <span className="ml-auto text-xs text-slate-500">{rows.length} rows × {colCount} cols</span>
                    </div>

                    <div className="flex-1 overflow-auto p-3">
                        <table className="border-collapse text-xs">
                            <thead className="sticky top-0 z-10">
                                <tr>
                                    <th className="sticky left-0 z-20 w-10 min-w-10 bg-slate-800 border border-slate-700 text-slate-500 font-normal" />
                                    {Array.from({ length: colCount }).map((_, c) => (
                                        <th key={c} className="group/col min-w-[8rem] bg-slate-800 border border-slate-700 px-2 py-1 text-center text-slate-400 font-semibold">
                                            <div className="flex items-center justify-center gap-1">
                                                {colLabel(c)}
                                                {colCount > 1 && (
                                                    <button type="button" onClick={() => deleteCol(c)} title="Delete column"
                                                        className="opacity-0 group-hover/col:opacity-100 text-slate-500 hover:text-red-400 transition-opacity">
                                                        <Trash2 className="h-3 w-3" />
                                                    </button>
                                                )}
                                            </div>
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row, r) => (
                                    <tr key={r} className="group/row">
                                        <td className="sticky left-0 z-10 w-10 min-w-10 bg-slate-800 border border-slate-700 text-center text-slate-500">
                                            <div className="flex items-center justify-center gap-1">
                                                <span>{r + 1}</span>
                                                {rows.length > 1 && (
                                                    <button type="button" onClick={() => deleteRow(r)} title="Delete row"
                                                        className="opacity-0 group-hover/row:opacity-100 text-slate-500 hover:text-red-400 transition-opacity">
                                                        <Trash2 className="h-3 w-3" />
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                        {row.map((cell, c) => (
                                            <td key={c} className="border border-slate-800 p-0">
                                                <input
                                                    value={cell}
                                                    onChange={(e) => setCell(r, c, e.target.value)}
                                                    className="w-full min-w-[8rem] bg-transparent px-2 py-1 text-slate-200 outline-none focus:bg-slate-800/60 focus:ring-1 focus:ring-inset focus:ring-primary"
                                                />
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}

            <div className="flex items-center justify-end gap-2 border-t border-slate-800 bg-slate-950/40 px-3 py-2">
                <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving} className="text-slate-400 hover:text-white">
                    <X className="h-4 w-4 mr-2" /> Cancel
                </Button>
                <Button type="button" size="sm" onClick={handleSave} disabled={saving || loading || !!error || !isDirty} className="bg-primary/90 hover:bg-primary text-white">
                    {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                    Save Changes
                </Button>
            </div>
        </div>
    );
}
