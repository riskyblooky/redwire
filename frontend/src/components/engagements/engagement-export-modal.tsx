'use client';

import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Download, ShieldAlert, KeyRound, ChevronDown, ChevronRight, Fingerprint, Copy, Check } from 'lucide-react';
import api, { apiErrorMessage } from '@/lib/api';
import { isAxiosError } from 'axios';
import { toast } from 'sonner';

const MIN_PW_LEN = 16;

export function EngagementExportModal({
    engagementId,
    engagementName,
    onClose,
}: {
    engagementId: string;
    engagementName: string;
    onClose: () => void;
}) {
    const [previewLoading, setPreviewLoading] = useState(true);
    const [containsSecrets, setContainsSecrets] = useState(false);
    const [vaultCount, setVaultCount] = useState(0);
    const [ack, setAck] = useState(false);
    const [showPwSection, setShowPwSection] = useState(false);
    const [passphrase, setPassphrase] = useState('');
    const [confirmPw, setConfirmPw] = useState('');
    const [busy, setBusy] = useState(false);
    const [rootDigest, setRootDigest] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        api.get(`/engagements/${engagementId}/export/preview`)
            .then((r) => {
                setContainsSecrets(!!r.data.contains_plaintext_secrets);
                setVaultCount(r.data.vault_item_count || 0);
            })
            .catch((err: any) => {
                toast.error(apiErrorMessage(err, 'Failed to load export preview'));
            })
            .finally(() => setPreviewLoading(false));
    }, [engagementId]);

    const pwTooShort = showPwSection && passphrase.length > 0 && passphrase.length < MIN_PW_LEN;
    const pwMismatch = showPwSection && passphrase.length > 0 && confirmPw.length > 0 && passphrase !== confirmPw;
    const pwIncomplete = showPwSection && (
        passphrase.length < MIN_PW_LEN ||
        confirmPw.length === 0 ||
        passphrase !== confirmPw
    );
    const ackBlocked = containsSecrets && !ack;
    const disabled = busy || previewLoading || ackBlocked || pwIncomplete;

    const handleExport = async () => {
        setBusy(true);
        try {
            // Through the shared axios instance (raw fetch skipped the 401
            // refresh, so an expired access token failed the export).
            const headers: Record<string, string> = {};
            if (showPwSection && passphrase) headers['X-Export-Passphrase'] = passphrase;
            let resp;
            try {
                resp = await api.get(`/engagements/${engagementId}/export`, { headers, responseType: 'blob' });
            } catch (err) {
                // responseType 'blob' → the error body is a Blob too.
                let parsed: unknown = isAxiosError(err) ? err.response?.data : undefined;
                if (parsed instanceof Blob) parsed = await parsed.text().then(t => JSON.parse(t)).catch(() => ({}));
                toast.error(apiErrorMessage({ response: { data: parsed } }, 'Export failed'));
                setBusy(false);
                return;
            }
            const digest = resp.headers['x-archive-root-digest'] as string | undefined;
            const blob = resp.data as Blob;
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const disposition = resp.headers['content-disposition'] as string | undefined;
            const match = disposition?.match(/filename="(.+)"/);
            a.download = match?.[1] || `${engagementName.replace(/\s+/g, '_')}_export.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            toast.success(showPwSection && passphrase ? 'Encrypted export downloaded' : 'Engagement exported successfully');
            const missing = Number(resp.headers['x-export-missing-files'] || 0);
            if (missing > 0) {
                toast.warning(`${missing} file${missing === 1 ? '' : 's'} could not be read from storage and ${missing === 1 ? 'is' : 'are'} not in the archive`, {
                    description: 'The archive manifest lists them under missing_files.',
                    duration: 15000,
                });
            }
            if (digest) {
                // Keep the modal open so the operator can copy the fingerprint
                // before dismissing (they'll want to share it out-of-band with
                // whoever will import).
                setRootDigest(digest);
                setBusy(false);
            } else {
                onClose();
            }
        } catch (err: any) {
            toast.error(err?.message || 'Export failed');
            setBusy(false);
        }
    };

    const copyDigest = async () => {
        if (!rootDigest) return;
        try {
            await navigator.clipboard.writeText(rootDigest);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            toast.error('Clipboard copy failed');
        }
    };

    return (
        <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
            <DialogContent className="sm:max-w-[560px] bg-slate-900 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        <Download className="h-5 w-5 text-blue-400" />
                        Export engagement
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Exporting <span className="text-white font-medium">{engagementName}</span> as a ZIP archive.
                    </DialogDescription>
                </DialogHeader>

                {rootDigest ? (
                    <div className="space-y-4 py-2">
                        <div className="rounded-lg border border-slate-700 bg-slate-950/50 p-4 space-y-2">
                            <div className="flex items-center gap-2 text-sm font-semibold text-blue-400">
                                <Fingerprint className="h-4 w-4" />
                                Archive fingerprint
                            </div>
                            <div className="flex items-center gap-2">
                                <code className="flex-1 font-mono text-xs text-slate-300 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 break-all">
                                    {rootDigest}
                                </code>
                                <Button size="icon" variant="outline" onClick={copyDigest} title="Copy">
                                    {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                                </Button>
                            </div>
                            <p className="text-xs text-slate-400">
                                Share this fingerprint with the recipient via a channel you trust
                                (Signal, in-person, encrypted email). They can compare it against
                                the fingerprint their instance computes on import to confirm the
                                archive hasn&apos;t been tampered with in transit.
                            </p>
                        </div>
                    </div>
                ) : previewLoading ? (
                    <div className="py-8 flex items-center justify-center text-slate-400 text-sm gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" /> Checking archive contents…
                    </div>
                ) : (
                    <div className="space-y-4 py-2">
                        {containsSecrets && (
                            <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 space-y-3">
                                <div className="flex items-start gap-3">
                                    <ShieldAlert className="h-5 w-5 text-red-400 mt-0.5 shrink-0" />
                                    <div className="text-sm text-slate-200 space-y-2">
                                        <p className="font-semibold text-red-400">
                                            This export will contain plaintext credentials.
                                        </p>
                                        <p className="text-slate-300">
                                            {vaultCount} vault item{vaultCount === 1 ? '' : 's'} on this engagement will be
                                            written into the archive in cleartext (passwords, notes, and any uploaded
                                            vault file attachments). Treat the resulting ZIP like a password file.
                                        </p>
                                    </div>
                                </div>
                                <label className="flex items-start gap-2 text-sm text-slate-200 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        className="mt-0.5 accent-primary"
                                        checked={ack}
                                        onChange={(e) => setAck(e.target.checked)}
                                    />
                                    <span>I understand this archive will contain plaintext secrets and will handle it accordingly.</span>
                                </label>
                            </div>
                        )}

                        <div className="rounded-lg border border-slate-700 bg-slate-950/50">
                            <button
                                type="button"
                                onClick={() => setShowPwSection((v) => !v)}
                                className="w-full flex items-center justify-between p-3 text-sm font-medium text-slate-200 hover:text-white"
                            >
                                <span className="flex items-center gap-2">
                                    <KeyRound className="h-4 w-4 text-violet-400" />
                                    Encrypt archive with passphrase (optional)
                                </span>
                                {showPwSection ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            </button>
                            {showPwSection && (
                                <div className="px-3 pb-3 space-y-3">
                                    <p className="text-xs text-slate-400">
                                        Wraps the ZIP in AES-256 (WinZip extension). The server never stores the
                                        passphrase — share it with the recipient out-of-band. Minimum {MIN_PW_LEN}{' '}
                                        characters.
                                    </p>
                                    <div className="space-y-1">
                                        <Label htmlFor="export-pw" className="text-xs text-slate-300">Passphrase</Label>
                                        <Input
                                            id="export-pw"
                                            type="password"
                                            autoComplete="new-password"
                                            value={passphrase}
                                            onChange={(e) => setPassphrase(e.target.value)}
                                            className="bg-slate-950 border-slate-700 text-white"
                                        />
                                        {pwTooShort && (
                                            <p className="text-xs text-red-400">Must be at least {MIN_PW_LEN} characters.</p>
                                        )}
                                    </div>
                                    <div className="space-y-1">
                                        <Label htmlFor="export-pw2" className="text-xs text-slate-300">Confirm passphrase</Label>
                                        <Input
                                            id="export-pw2"
                                            type="password"
                                            autoComplete="new-password"
                                            value={confirmPw}
                                            onChange={(e) => setConfirmPw(e.target.value)}
                                            className="bg-slate-950 border-slate-700 text-white"
                                        />
                                        {pwMismatch && (
                                            <p className="text-xs text-red-400">Passphrases don&apos;t match.</p>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                <DialogFooter>
                    {rootDigest ? (
                        <Button onClick={onClose}>Done</Button>
                    ) : (
                        <>
                            <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
                            <Button onClick={handleExport} disabled={disabled}>
                                {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Download className="h-4 w-4 mr-2" />}
                                {showPwSection && passphrase ? 'Download encrypted archive' : 'Download archive'}
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
