'use client';

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Upload, ShieldAlert, CheckCircle2, AlertCircle, Briefcase, Bug, Server, ListChecks,
    Paperclip, KeyRound, StickyNote, Brush, MessageSquare, Network, FileText,
} from 'lucide-react';

export interface ImportPreview {
    engagement_name: string;
    engagement: {
        name: string;
        client_name?: string | null;
        engagement_type?: string | null;
        status?: string | null;
        start_date?: string | null;
        end_date?: string | null;
        description?: string | null;
    };
    archive: {
        exported_at?: string | null;
        source_version?: string | null;
        contains_plaintext_secrets: boolean;
    };
    counts: Record<string, number>;
    matched_users: any[];
    unmatched_users: any[];
    local_users: any[];
}

const COUNT_ROWS: Array<{ key: string; label: string; Icon: any }> = [
    { key: 'findings', label: 'Findings', Icon: Bug },
    { key: 'assets', label: 'Assets', Icon: Server },
    { key: 'testcases', label: 'Test cases', Icon: ListChecks },
    { key: 'evidence', label: 'Evidence files', Icon: Paperclip },
    { key: 'vault_items', label: 'Vault items', Icon: KeyRound },
    { key: 'notes', label: 'Notes', Icon: StickyNote },
    { key: 'cleanup_artifacts', label: 'Cleanup artifacts', Icon: Brush },
    { key: 'threads', label: 'Discussion threads', Icon: MessageSquare },
    { key: 'attacker_nodes', label: 'Attacker nodes', Icon: Network },
    { key: 'report_layouts', label: 'Report layouts', Icon: FileText },
];

function fmtDate(s?: string | null) {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString(); } catch { return s; }
}

export function EngagementImportPreviewModal({
    preview,
    onCancel,
    onConfirm,
    isImporting,
}: {
    preview: ImportPreview;
    onCancel: () => void;
    onConfirm: () => void;
    isImporting: boolean;
}) {
    const matched = preview.matched_users.length;
    const unmatched = preview.unmatched_users.length;
    const totalUsers = matched + unmatched;

    return (
        <Dialog open onOpenChange={(open) => { if (!open && !isImporting) onCancel(); }}>
            <DialogContent className="sm:max-w-[640px] bg-slate-900 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        <Upload className="h-5 w-5 text-blue-400" />
                        Import preview
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Review what's in this archive before creating the engagement on this instance.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    {/* Engagement header */}
                    <div className="rounded-lg border border-slate-700 bg-slate-950/50 p-4 space-y-2">
                        <div className="flex items-start gap-3">
                            <Briefcase className="h-5 w-5 text-blue-400 mt-0.5 shrink-0" />
                            <div className="min-w-0 flex-1">
                                <div className="text-white font-semibold truncate">{preview.engagement.name}</div>
                                {preview.engagement.client_name && (
                                    <div className="text-sm text-slate-400 truncate">
                                        Client: <span className="text-slate-300">{preview.engagement.client_name}</span>
                                    </div>
                                )}
                            </div>
                            {preview.engagement.status && (
                                <Badge variant="outline" className="border-slate-600 text-slate-300 shrink-0">
                                    {String(preview.engagement.status).replace(/_/g, ' ')}
                                </Badge>
                            )}
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-400 pl-8">
                            {preview.engagement.engagement_type && (
                                <div>Type: <span className="text-slate-300">{preview.engagement.engagement_type}</span></div>
                            )}
                            <div>Start: <span className="text-slate-300">{fmtDate(preview.engagement.start_date)}</span></div>
                            <div>End: <span className="text-slate-300">{fmtDate(preview.engagement.end_date)}</span></div>
                            {preview.archive.exported_at && (
                                <div>Archive built: <span className="text-slate-300">{fmtDate(preview.archive.exported_at)}</span></div>
                            )}
                        </div>
                        {preview.engagement.description && (
                            <div className="pl-8 text-xs text-slate-400">
                                <span className="text-slate-500">Description:</span>{' '}
                                <span className="text-slate-300">{preview.engagement.description}</span>
                            </div>
                        )}
                    </div>

                    {/* Plaintext-secrets banner */}
                    {preview.archive.contains_plaintext_secrets && (
                        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 flex items-start gap-3">
                            <ShieldAlert className="h-5 w-5 text-red-400 mt-0.5 shrink-0" />
                            <div className="text-sm text-slate-200">
                                <p className="font-semibold text-red-400">Archive contains plaintext vault secrets.</p>
                                <p className="text-slate-300 mt-0.5">
                                    They will be re-encrypted under this instance's VAULT_ENCRYPTION_KEY on import.
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Counts */}
                    <div className="rounded-lg border border-slate-700 bg-slate-950/50 p-3">
                        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                            Archive contents
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                            {COUNT_ROWS.map(({ key, label, Icon }) => {
                                const n = preview.counts[key] ?? 0;
                                return (
                                    <div
                                        key={key}
                                        className={`flex items-center justify-between text-sm py-0.5 ${n === 0 ? 'text-slate-500' : 'text-slate-200'}`}
                                    >
                                        <span className="flex items-center gap-1.5">
                                            <Icon className="h-3.5 w-3.5" />
                                            {label}
                                        </span>
                                        <span className="font-mono tabular-nums">{n}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Users summary */}
                    {totalUsers > 0 && (
                        <div className="rounded-lg border border-slate-700 bg-slate-950/50 p-3 space-y-1.5">
                            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                                Users referenced in archive
                            </div>
                            <div className="flex items-center gap-3 text-sm">
                                <span className="flex items-center gap-1.5 text-emerald-400">
                                    <CheckCircle2 className="h-4 w-4" /> {matched} matched
                                </span>
                                {unmatched > 0 && (
                                    <span className="flex items-center gap-1.5 text-amber-400">
                                        <AlertCircle className="h-4 w-4" /> {unmatched} unmatched
                                    </span>
                                )}
                            </div>
                            {unmatched > 0 && (
                                <div className="text-xs text-slate-400">
                                    You'll be asked to map unmatched users to local accounts next, or accept
                                    the fallback (records get attributed to you).
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onCancel} disabled={isImporting}>Cancel</Button>
                    <Button onClick={onConfirm} disabled={isImporting}>
                        <Upload className="h-4 w-4 mr-2" />
                        {unmatched > 0 ? 'Continue to user mapping' : 'Import engagement'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
