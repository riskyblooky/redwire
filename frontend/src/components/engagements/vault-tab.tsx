'use client';

import { useState, useEffect, useMemo } from 'react';
import { useVaultItems, VaultItem, VaultItemReveal, useLinkVaultToFinding, useUnlinkVaultFromFinding, useLinkVaultToTestCase, useUnlinkVaultFromTestCase, useLinkVaultToAsset, useUnlinkVaultFromAsset } from '@/lib/hooks/use-vault';
import { useCheckPassword, useLookupHash } from '@/lib/hooks/use-wordlist';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useAssets } from '@/lib/hooks/use-assets';
import { useNotes } from '@/lib/hooks/use-notes';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Lock, Key, Shield, Eye, EyeOff, Copy, Trash2, Plus,
    MoreVertical, Loader2, Download, Search, Check, CheckCircle, AlertCircle, User as UserIcon, FileKey, Bug, CheckSquare, Link as LinkIcon, X, XCircle, StickyNote, Zap, AlertTriangle, Hash,
    LayoutGrid, List, ArrowUpDown, Server, Target,
} from 'lucide-react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { LinkTooltip } from '@/components/ui/link-tooltip';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useCanEdit, useCanDelete, usePermission } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { UserAvatar } from '@/components/ui/user-avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { SprayTracker } from './spray-tracker';
import { LinkEntityDialog, LinkedIdMap, LinkResourceType } from '@/components/ui/link-entity-dialog';

interface VaultTabProps {
    engagementId: string;
}

const VaultItemCard = ({
    item,
    engagementId,
    getItemIcon,
    handleDeleteItem,
    togglePassword,
    copyToClipboard,
    revealedItems,
    revealAndGet,
    copiedId,
    handleSecureDownload,
    onEdit,
    onLink
}: any) => {
    const canDeleteVault = useCanDelete(engagementId, 'vault', item.created_by);
    const canEditVault = useCanEdit(engagementId, 'vault', item.created_by);
    const noteCount = item._noteCount || 0;

    // GHSA-fp69-w2mg-4pqp: ``item`` carries metadata only; the
    // decrypted plaintext lives in ``revealedItems[item.id]`` after the
    // user toggles the eye. Until then, password renders as bullets and
    // username renders as "USER SET" (or empty if has_username is
    // false). The hash-shape badge is driven by the server-computed
    // ``item.password_looks_like_hash`` so it doesn't force a reveal.
    const revealed = revealedItems[item.id];
    const isRevealed = !!revealed;

    // Wordlist check state
    const checkPassword = useCheckPassword();
    const lookupHash = useLookupHash();
    const [wordlistResult, setWordlistResult] = useState<'unchecked' | 'checking' | 'found' | 'safe'>('unchecked');
    const [crackResult, setCrackResult] = useState<{ status: 'idle' | 'cracking' | 'cracked' | 'not_found'; password?: string; hashType?: string; note?: string }>({ status: 'idle' });

    // Reveal-then-act helpers. Each callback triggers a reveal call if
    // the plaintext isn't already cached — the server dedups per
    // (user, item) over 5 minutes so we don't multiply audit rows for
    // rapid-fire interactions.
    const handleCheckWordlist = async () => {
        if (!item.has_password) return;
        setWordlistResult('checking');
        try {
            const data = await revealAndGet(item.id);
            if (!data?.password) {
                setWordlistResult('unchecked');
                return;
            }
            const res = await checkPassword.mutateAsync(data.password);
            setWordlistResult(res.found ? 'found' : 'safe');
        } catch {
            setWordlistResult('unchecked');
        }
    };

    const handleCrackHash = async () => {
        if (!item.has_password) return;
        setCrackResult({ status: 'cracking' });
        try {
            const data = await revealAndGet(item.id);
            if (!data?.password) {
                setCrackResult({ status: 'idle' });
                return;
            }
            const res = await lookupHash.mutateAsync(data.password);
            if (res.found) {
                setCrackResult({ status: 'cracked', password: res.password, hashType: res.hash_type });
            } else {
                setCrackResult({ status: 'not_found', note: res.note });
            }
        } catch {
            setCrackResult({ status: 'idle' });
        }
    };

    // Copy-to-clipboard helper that reveals first if needed. Routes
    // through the same reveal flow so a user clicking "copy password"
    // produces an audit row even if they never opened the eye.
    const handleCopyField = async (field: 'username' | 'password' | 'note', copiedKey: string) => {
        const data = revealed || (await revealAndGet(item.id));
        const value = data?.[field];
        if (value) copyToClipboard(value, copiedKey);
    };

    return (
        <Card key={item.id} className="border-slate-800 bg-slate-900/40 backdrop-blur-xs hover:border-indigo-500/30 transition-all duration-300 group overflow-hidden">
            <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-slate-800 border border-slate-700">
                            {getItemIcon(item.item_type)}
                        </div>
                        <CardTitle className="text-sm font-bold text-white truncate max-w-[150px]">
                            {item.name}
                        </CardTitle>
                    </div>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-white">
                                <MoreVertical className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white">
                            {canEditVault && (
                                <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={() => onEdit(item)}>
                                    <Plus className="h-4 w-4 mr-2" />
                                    Edit Details
                                </DropdownMenuItem>
                            )}
                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={() => onLink(item)}>
                                <LinkIcon className="h-4 w-4 mr-2" />
                                Link Resources
                            </DropdownMenuItem>
                            {canDeleteVault && (
                                <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={() => handleDeleteItem(item.id)}>
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    Delete Permanent
                                </DropdownMenuItem>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
                <CardDescription className="text-[10px] text-slate-500 mt-1 flex items-center gap-1.5">
                    <TooltipProvider delayDuration={200}>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <span className="w-fit">
                                    <UserAvatar
                                        user={{
                                            id: item.created_by,
                                            username: item.created_by_username || 'System',
                                            profile_photo: item.created_by_profile_photo,
                                        }}
                                        className="h-4 w-4 text-[6px]"
                                    />
                                </span>
                            </TooltipTrigger>
                            <TooltipContent side="top">
                                <span className="text-xs">{item.created_by_username || 'System'}</span>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                    • {new Date(item.created_at).toLocaleString()}
                </CardDescription>
            </CardHeader>

            <CardContent className="p-4 pt-2 space-y-4">
                {item.description && (
                    <p className="text-[11px] text-slate-400 line-clamp-2 italic">
                        "{item.description}"
                    </p>
                )}

                <div className="bg-slate-950/50 rounded-xl p-3 border border-slate-800/50 space-y-3">
                    {item.item_type === 'CREDENTIAL' && (
                        <>
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Username</span>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-white font-medium">
                                        {isRevealed ? (revealed?.username || '—') : (item.has_username ? '•••' : '—')}
                                    </span>
                                    {item.has_username && (
                                        <Button
                                            variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0"
                                            onClick={() => handleCopyField('username', `${item.id}-usr`)}
                                        >
                                            {copiedId === `${item.id}-usr` ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                                        </Button>
                                    )}
                                </div>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Password</span>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-indigo-400 font-mono">
                                        {isRevealed ? (revealed?.password || '—') : (item.has_password ? '••••••••••••' : '—')}
                                    </span>
                                    <div className="flex items-center gap-1">
                                        <Button
                                            variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0"
                                            onClick={() => togglePassword(item.id)}
                                            disabled={!item.has_password && !item.has_username && !item.has_note}
                                        >
                                            {isRevealed ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                        </Button>
                                        {item.has_password && (
                                            <Button
                                                variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0"
                                                onClick={() => handleCopyField('password', `${item.id}-pwd`)}
                                            >
                                                {copiedId === `${item.id}-pwd` ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </div>
                            {/* Wordlist Check / Hash Crack Actions */}
                            {item.has_password && (
                                <div className="flex flex-wrap items-center gap-1.5 mt-1">
                                    {/* Check against wordlist */}
                                    {wordlistResult === 'unchecked' && (
                                        <Button
                                            variant="outline" size="sm"
                                            className="h-6 text-[10px] px-2 border-slate-700 bg-slate-800/50 hover:bg-slate-700 text-slate-300"
                                            onClick={handleCheckWordlist}
                                        >
                                            <Zap className="h-3 w-3 mr-1" />
                                            Check Wordlist
                                        </Button>
                                    )}
                                    {wordlistResult === 'checking' && (
                                        <Badge className="bg-slate-800 text-slate-400 border-slate-700 text-[10px] gap-1">
                                            <Loader2 className="h-3 w-3 animate-spin" /> Checking…
                                        </Badge>
                                    )}
                                    {wordlistResult === 'found' && (
                                        <Badge className="bg-red-500/10 text-red-400 border-red-500/20 text-[10px] gap-1">
                                            <AlertTriangle className="h-3 w-3" /> In Wordlist!
                                        </Badge>
                                    )}
                                    {wordlistResult === 'safe' && (
                                        <Badge className="bg-green-500/10 text-green-400 border-green-500/20 text-[10px] gap-1">
                                            <CheckCircle className="h-3 w-3" /> Not Found
                                        </Badge>
                                    )}

                                    {/* Crack hash button (driven by server-side classification — no reveal needed to surface the affordance). */}
                                    {item.password_looks_like_hash && crackResult.status === 'idle' && (
                                        <Button
                                            variant="outline" size="sm"
                                            className="h-6 text-[10px] px-2 border-amber-700/50 bg-amber-900/20 hover:bg-amber-900/30 text-amber-400"
                                            onClick={handleCrackHash}
                                        >
                                            <Hash className="h-3 w-3 mr-1" />
                                            Crack Hash
                                        </Button>
                                    )}
                                    {crackResult.status === 'cracking' && (
                                        <Badge className="bg-slate-800 text-slate-400 border-slate-700 text-[10px] gap-1">
                                            <Loader2 className="h-3 w-3 animate-spin" /> Cracking…
                                        </Badge>
                                    )}
                                    {crackResult.status === 'cracked' && (
                                        <div className="flex items-center gap-1.5">
                                            <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px] gap-1">
                                                <CheckCircle className="h-3 w-3" /> {crackResult.hashType?.toUpperCase()}
                                            </Badge>
                                            <span className="text-xs text-emerald-400 font-mono font-bold">{crackResult.password}</span>
                                            <Button
                                                variant="ghost" size="icon" className="h-4 w-4 text-emerald-400 p-0"
                                                onClick={() => copyToClipboard(crackResult.password!, `${item.id}-cracked`)}
                                            >
                                                {copiedId === `${item.id}-cracked` ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                            </Button>
                                        </div>
                                    )}
                                    {crackResult.status === 'not_found' && (
                                        <Badge className="bg-slate-800 text-slate-500 border-slate-700 text-[10px] gap-1" title={crackResult.note}>
                                            <XCircle className="h-3 w-3" /> No Match
                                        </Badge>
                                    )}
                                </div>
                            )}
                        </>
                    )}

                    {item.item_type === 'FILE' && (
                        <div className="flex flex-col gap-2">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Filename</span>
                                <span className="text-xs text-white truncate max-w-[120px]">{item.filename}</span>
                            </div>
                            <Button
                                variant="outline" size="sm"
                                className="w-full text-xs border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 h-8"
                                onClick={() => {
                                    handleSecureDownload(item.id, item.filename || 'file');
                                }}
                            >
                                <Download className="h-3 w-3 mr-2" />
                                Download Securely
                            </Button>
                        </div>
                    )}

                    {(item.item_type === 'NOTE' || item.item_type === 'KEY') && (
                        <div className="flex flex-col gap-2">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Content</span>
                                <div className="flex items-center gap-1">
                                    <Button
                                        variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0"
                                        onClick={() => togglePassword(item.id)}
                                        disabled={!item.has_note}
                                    >
                                        {isRevealed ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                    </Button>
                                    {item.has_note && (
                                        <Button
                                            variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0"
                                            onClick={() => handleCopyField('note', item.id)}
                                        >
                                            {copiedId === item.id ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                                        </Button>
                                    )}
                                </div>
                            </div>
                            <div className="bg-slate-900/80 rounded-lg p-2 max-h-24 overflow-y-auto">
                                <p className="text-[10px] font-mono whitespace-pre-wrap text-slate-300">
                                    {isRevealed ? (revealed?.note || 'No content') : (item.has_note ? '••••••••' : 'No content')}
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Linked items footer */}
                {((item.findings && item.findings.length > 0) || (item.testcases && item.testcases.length > 0) || (item.assets && item.assets.length > 0) || noteCount > 0) && (
                    <div className="flex items-center gap-3 pt-2 border-t border-slate-800/50 mt-2">
                        <LinkTooltip
                            icon={<Bug className="h-3 w-3" />}
                            count={item.findings?.length || 0}
                            items={(item.findings || []).map((f: any) => ({ name: f.title, href: `/findings/${f.id}?engagementId=${engagementId}` }))}
                            label="Findings"
                            colorClass="text-red-400"
                            countClass="text-[10px] font-bold"
                        />
                        <LinkTooltip
                            icon={<CheckSquare className="h-3 w-3" />}
                            count={item.testcases?.length || 0}
                            items={(item.testcases || []).map((t: any) => ({ name: t.title, href: `/testcases/${t.id}?engagementId=${engagementId}` }))}
                            label="Test Cases"
                            colorClass="text-emerald-400"
                            countClass="text-[10px] font-bold"
                        />
                        <LinkTooltip
                            icon={<Server className="h-3 w-3" />}
                            count={item.assets?.length || 0}
                            items={(item.assets || []).map((a: any) => ({ name: a.name || a.identifier, href: `/assets/${a.id}` }))}
                            label="Assets"
                            colorClass="text-blue-400"
                            countClass="text-[10px] font-bold"
                        />
                        <LinkTooltip
                            icon={<StickyNote className="h-3 w-3" />}
                            count={noteCount}
                            items={[]}
                            label="Notes"
                            colorClass="text-teal-400"
                            countClass="text-[10px] font-bold"
                        />
                    </div>
                )}
            </CardContent>
        </Card>
    );
};

// ── Vault Item Row (Table view) ──
const VaultItemRow = ({
    item, engagementId, getItemIcon, handleDeleteItem, togglePassword,
    copyToClipboard, revealedItems, revealAndGet, copiedId, handleSecureDownload, onEdit, onLink
}: any) => {
    const canDeleteVault = useCanDelete(engagementId, 'vault', item.created_by);
    const canEditVault = useCanEdit(engagementId, 'vault', item.created_by);
    const noteCount = item._noteCount || 0;
    // GHSA-fp69-w2mg-4pqp: see VaultItemCard for the parallel rationale.
    const revealed = revealedItems[item.id];
    const isRevealed = !!revealed;
    const handleCopyField = async (field: 'username' | 'password' | 'note', copiedKey: string) => {
        const data = revealed || (await revealAndGet(item.id));
        const value = data?.[field];
        if (value) copyToClipboard(value, copiedKey);
    };
    return (
        <div className="group flex items-center gap-3 px-4 py-2.5 bg-slate-900/40 hover:bg-slate-900/70 border border-slate-800 rounded-xl transition-colors">
            {/* Icon + Name */}
            <div className="flex items-center gap-2 w-48 min-w-0 flex-shrink-0">
                <div className="p-1 rounded-md bg-slate-800 border border-slate-700 flex-shrink-0">
                    {getItemIcon(item.item_type)}
                </div>
                <span className="text-xs font-semibold text-white truncate">{item.name}</span>
            </div>
            {/* Type badge */}
            <div className="w-24 flex-shrink-0">
                <Badge variant="outline" className="text-[9px] border-slate-700 text-slate-400 uppercase tracking-wider">{item.item_type}</Badge>
            </div>
            {/* Username / content preview - equal flex share with password */}
            <div className="flex-[2] min-w-0 text-xs text-slate-400 truncate">
                {item.item_type === 'CREDENTIAL' && (isRevealed ? (revealed?.username || '—') : (item.has_username ? '•••' : '—'))}
                {item.item_type === 'FILE' && (item.filename || '—')}
                {(item.item_type === 'NOTE' || item.item_type === 'KEY') && (
                    <span className="font-mono text-[10px]">
                        {isRevealed
                            ? ((revealed?.note || '').slice(0, 40) + ((revealed?.note || '').length > 40 ? '…' : ''))
                            : (item.has_note ? '••••••••' : '')}
                    </span>
                )}
            </div>
            {/* Password field - equal flex share with content */}
            {item.item_type === 'CREDENTIAL' ? (
                <div className="flex items-center gap-1 flex-[2] min-w-0">
                    <span className="text-xs font-mono text-primary truncate max-w-[90px]">
                        {isRevealed ? (revealed?.password || '—') : (item.has_password ? '••••••••' : '—')}
                    </span>
                    <Button variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0 flex-shrink-0" onClick={() => togglePassword(item.id)}>
                        {isRevealed ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                    </Button>
                    {item.has_password && (
                        <Button variant="ghost" size="icon" className="h-5 w-5 text-slate-500 p-0 flex-shrink-0" onClick={() => handleCopyField('password', `${item.id}-pwd`)}>
                            {copiedId === `${item.id}-pwd` ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                        </Button>
                    )}
                </div>
            ) : <div className="flex-[2] min-w-0" />}
            {/* Links - icon + count, hover for names */}
            <div className="flex items-center gap-2.5 w-32 flex-shrink-0">
                <LinkTooltip
                    icon={<Bug className="h-3 w-3" />}
                    count={item.findings?.length || 0}
                    items={(item.findings || []).map((f: any) => ({ name: f.title, href: `/findings/${f.id}?engagementId=${engagementId}` }))}
                    label="Findings"
                    colorClass="text-red-400"
                    countClass="text-[10px] font-bold"
                />
                <LinkTooltip
                    icon={<CheckSquare className="h-3 w-3" />}
                    count={item.testcases?.length || 0}
                    items={(item.testcases || []).map((t: any) => ({ name: t.title, href: `/testcases/${t.id}?engagementId=${engagementId}` }))}
                    label="Test Cases"
                    colorClass="text-emerald-400"
                    countClass="text-[10px] font-bold"
                />
                <LinkTooltip
                    icon={<Server className="h-3 w-3" />}
                    count={item.assets?.length || 0}
                    items={(item.assets || []).map((a: any) => ({ name: a.name || a.identifier, href: `/assets/${a.id}` }))}
                    label="Assets"
                    colorClass="text-blue-400"
                    countClass="text-[10px] font-bold"
                />
                <LinkTooltip
                    icon={<StickyNote className="h-3 w-3" />}
                    count={noteCount}
                    items={[]}
                    label="Notes"
                    colorClass="text-teal-400"
                    countClass="text-[10px] font-bold"
                />
            </div>
            {/* Creator avatar (hover for username) */}
            <div className="w-6 flex-shrink-0">
                <TooltipProvider delayDuration={200}>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <span className="inline-block">
                                <UserAvatar
                                    user={{
                                        id: item.created_by,
                                        username: item.created_by_username || 'System',
                                        profile_photo: item.created_by_profile_photo,
                                    }}
                                    className="h-5 w-5 text-[8px]"
                                />
                            </span>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                            <span className="text-xs">{item.created_by_username || 'System'}</span>
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </div>
            {/* Date + time */}
            <div className="w-40 flex-shrink-0 text-[10px] text-slate-500">
                {new Date(item.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'medium' })}
            </div>
            {/* Actions */}
            <div className="flex-shrink-0">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-white">
                            <MoreVertical className="h-3.5 w-3.5" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white">
                        {canEditVault && (
                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={() => onEdit(item)}>
                                <Plus className="h-4 w-4 mr-2" /> Edit Details
                            </DropdownMenuItem>
                        )}
                        <DropdownMenuItem className="text-slate-300 focus:bg-slate-800/50 focus:text-white" onClick={() => onLink(item)}>
                            <LinkIcon className="h-4 w-4 mr-2" /> Link Resources
                        </DropdownMenuItem>
                        {item.item_type === 'FILE' && (
                            <DropdownMenuItem className="text-slate-300 focus:bg-slate-800" onClick={() => handleSecureDownload(item.id, item.filename || 'file')}>
                                <Download className="h-4 w-4 mr-2" /> Download
                            </DropdownMenuItem>
                        )}
                        {canDeleteVault && (
                            <DropdownMenuItem className="text-red-400 focus:bg-red-500/10 focus:text-red-400" onClick={() => handleDeleteItem(item.id)}>
                                <Trash2 className="h-4 w-4 mr-2" /> Delete
                            </DropdownMenuItem>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
        </div>
    );
};

export function VaultTab({ engagementId }: VaultTabProps) {
    const { data: items = [], isLoading, refetch } = useVaultItems(engagementId);
    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: assets = [] } = useAssets(engagementId);
    const { data: notes = [] } = useNotes(engagementId);

    // Compute note count per vault item
    const noteCountByVaultItem = useMemo(() => {
        const map: Record<string, number> = {};
        notes.forEach(n => n.linked_vault_items?.forEach(v => { map[v.id] = (map[v.id] || 0) + 1; }));
        return map;
    }, [notes]);
    const linkToFinding = useLinkVaultToFinding();
    const unlinkFromFinding = useUnlinkVaultFromFinding();
    const linkToTestCase = useLinkVaultToTestCase();
    const unlinkFromTestCase = useUnlinkVaultFromTestCase();
    const linkToAsset = useLinkVaultToAsset();
    const unlinkFromAsset = useUnlinkVaultFromAsset();

    // Permission guards
    const canCreateVault = usePermission(engagementId, 'vault_create');
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // View preferences
    const [viewMode, setViewMode] = useState<'tile' | 'table'>(() =>
        (typeof window !== 'undefined' ? localStorage.getItem('vault-view-mode') : null) as 'tile' | 'table' || 'tile'
    );
    const setView = (mode: 'tile' | 'table') => {
        setViewMode(mode);
        localStorage.setItem('vault-view-mode', mode);
    };

    // Sort + filter state
    const [sortBy, setSortBy] = useState<'name' | 'date' | 'type'>('date');
    const [filterType, setFilterType] = useState<'ALL' | 'CREDENTIAL' | 'KEY' | 'FILE' | 'NOTE'>('ALL');

    // Link dialog state — uses the shared LinkEntityDialog
    const [isLinkDialogOpen, setIsLinkDialogOpen] = useState(false);
    const [linkingItem, setLinkingItem] = useState<VaultItem | null>(null);

    const handleOpenLinkDialog = (item: VaultItem) => {
        setLinkingItem(item);
        setIsLinkDialogOpen(true);
    };

    const handleEntityLink = async (type: LinkResourceType, resourceId: string) => {
        if (!linkingItem) return;
        const args = { vaultItemId: linkingItem.id };
        if (type === 'findings') await linkToFinding.mutateAsync({ ...args, findingId: resourceId });
        if (type === 'testcases') await linkToTestCase.mutateAsync({ ...args, testcaseId: resourceId });
        if (type === 'assets') await linkToAsset.mutateAsync({ ...args, assetId: resourceId });
    };
    const handleEntityUnlink = async (type: LinkResourceType, resourceId: string) => {
        if (!linkingItem) return;
        const args = { vaultItemId: linkingItem.id };
        if (type === 'findings') await unlinkFromFinding.mutateAsync({ ...args, findingId: resourceId });
        if (type === 'testcases') await unlinkFromTestCase.mutateAsync({ ...args, testcaseId: resourceId });
        if (type === 'assets') await unlinkFromAsset.mutateAsync({ ...args, assetId: resourceId });
    };

    const linkingItemLinkedIds: LinkedIdMap = {
        findings: new Set((linkingItem?.findings ?? []).map((f: any) => f.id)),
        testcases: new Set((linkingItem?.testcases ?? []).map((t: any) => t.id)),
        assets: new Set((linkingItem?.assets ?? []).map((a: any) => a.id)),
        vault: new Set(),
        cleanup: new Set(),
        intel: new Set(),
        infra: new Set(),
    };



    const [searchQuery, setSearchQuery] = useState('');
    const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
    const [newItem, setNewItem] = useState<{
        name: string;
        item_type: 'CREDENTIAL' | 'KEY' | 'FILE' | 'NOTE';
        username: string;
        password: string;
        note: string;
        description: string;
    }>({
        name: '',
        item_type: 'CREDENTIAL',
        username: '',
        password: '',
        note: '',
        description: ''
    });
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    // GHSA-fp69-w2mg-4pqp follow-up: the list response carries metadata
    // only. ``revealedItems`` stores the decrypted plaintext for items
    // the user has explicitly toggled open via the eye-icon. Presence in
    // the map means "revealed"; absence means "masked". The server
    // dedups the audit log per (user, item) over 5 minutes so multiple
    // toggles in quick succession don't multiply the log rows.
    const [revealedItems, setRevealedItems] = useState<Record<string, VaultItemReveal | undefined>>({});
    const [copiedId, setCopiedId] = useState<string | null>(null);

    const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
    const [editingItem, setEditingItem] = useState<VaultItem | null>(null);
    const [editForm, setEditForm] = useState({
        name: '',
        username: '',
        password: '',
        note: '',
        description: ''
    });

    const handleEditItem = async (item: VaultItem) => {
        // Need plaintext to seed the edit form so the user sees the
        // current values. Reveal triggers an audit row (deduped per
        // 5min) — editing a credential is itself an access event.
        const revealed = await revealAndGet(item.id);
        if (!revealed) return;
        setEditingItem(item);
        setEditForm({
            name: revealed.name || '',
            username: revealed.username || '',
            password: revealed.password || '',
            note: revealed.note || '',
            description: revealed.description || ''
        });
        setIsEditDialogOpen(true);
    };

    const handleUpdateItem = async () => {
        if (!editingItem) return;
        setIsSubmitting(true);
        try {
            await api.patch(`/vault/${editingItem.id}`, editForm);
            toast.success('Vault item updated');
            setIsEditDialogOpen(false);
            setEditingItem(null);
            refetch();
        } catch (error: any) {
            const detail = error?.response?.data?.detail || error.message;
            console.error('Failed to update vault item:', detail, error);
            toast.error(`Failed to update: ${detail}`);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleAddItem = async () => {
        // Validate required fields
        if (!newItem.name.trim()) {
            toast.error('Item name is required');
            return;
        }
        if (newItem.item_type === 'CREDENTIAL' && !newItem.username.trim() && !newItem.password.trim()) {
            toast.error('At least a username or password is required for credentials');
            return;
        }
        if (newItem.item_type === 'KEY' && !newItem.note.trim()) {
            toast.error('Key content is required');
            return;
        }
        if (newItem.item_type === 'NOTE' && !newItem.note.trim()) {
            toast.error('Note content is required');
            return;
        }
        if (newItem.item_type === 'FILE' && !selectedFile) {
            toast.error('Please select a file to upload');
            return;
        }

        setIsSubmitting(true);
        try {
            if (newItem.item_type === 'FILE' && selectedFile) {
                const formData = new FormData();
                formData.append('engagement_id', engagementId);
                formData.append('name', newItem.name);
                if (newItem.description.trim()) {
                    formData.append('description', newItem.description);
                }
                formData.append('file', selectedFile);
                await api.post('/vault/upload', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
            } else {
                await api.post('/vault', { ...newItem, engagement_id: engagementId });
            }
            toast.success('Vault item created');
            setNewItem({
                name: '',
                item_type: 'CREDENTIAL',
                username: '',
                password: '',
                note: '',
                description: ''
            });
            setSelectedFile(null);
            setIsAddDialogOpen(false);
            refetch();
        } catch (error: any) {
            console.error('Failed to add vault item:', error);
            const detail = error?.response?.data?.detail;
            const msg = Array.isArray(detail)
                ? detail.map((d: any) => d.msg || String(d)).join('; ')
                : (typeof detail === 'string' ? detail : 'Failed to add item to vault');
            toast.error(msg);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleDeleteItem = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Vault Item',
            description: 'Are you sure you want to delete this vault item? This cannot be undone.',
        });
        if (!confirmed) return;

        try {
            await api.delete(`/vault/${id}`);
            refetch();
        } catch (error: any) {
            console.error('Failed to delete vault item:', error);
            toast.error(getErrorMessage(error, 'Failed to delete vault item'));
        }
    };

    // Fetch & cache the decrypted plaintext for an item. Used by the
    // eye-icon toggle, copy-to-clipboard, wordlist/hash actions, and
    // the edit dialog opener — every path that needs ciphertext-back.
    const revealAndGet = async (id: string): Promise<VaultItemReveal | null> => {
        if (revealedItems[id]) return revealedItems[id]!;
        try {
            const { data } = await api.get<VaultItemReveal>(`/vault/${id}/reveal`);
            setRevealedItems(prev => ({ ...prev, [id]: data }));
            return data;
        } catch (e) {
            console.error('Failed to reveal vault item:', e);
            toast.error('Failed to reveal credential');
            return null;
        }
    };

    const togglePassword = async (id: string) => {
        if (revealedItems[id]) {
            // Mask: clear the cached plaintext. A subsequent unmask will
            // re-fetch — but the server dedups within 5 min so it
            // won't log a fresh row unless that window has elapsed.
            setRevealedItems(prev => {
                const next = { ...prev };
                delete next[id];
                return next;
            });
        } else {
            await revealAndGet(id);
        }
    };

    const handleSecureDownload = async (itemId: string, filename: string) => {
        try {
            const response = await api.get(`/vault/download/${itemId}`, {
                responseType: 'blob'
            });
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            window.open(url, '_blank');
            link.remove();
        } catch (error) {
            console.error('Download failed:', error);
            toast.error('Failed to download file securely');
        }
    };

    const copyToClipboard = (text: string, id: string) => {
        navigator.clipboard.writeText(text);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const processedItems = useMemo(() => {
        // username search dropped from the client-side filter — the list
        // response no longer carries the plaintext to match against,
        // and revealing every item just to match a search would defeat
        // the audit-log discipline. Name / type / description remain;
        // those are visible-by-design metadata.
        let result = items.filter(item => {
            const matchesSearch =
                item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                item.item_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
                item.description?.toLowerCase().includes(searchQuery.toLowerCase());
            const matchesType = filterType === 'ALL' || item.item_type === filterType;
            return matchesSearch && matchesType;
        });
        result = [...result].sort((a, b) => {
            if (sortBy === 'name') return a.name.localeCompare(b.name);
            if (sortBy === 'type') return a.item_type.localeCompare(b.item_type);
            return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        });
        return result;
    }, [items, searchQuery, filterType, sortBy]);

    const getItemIcon = (type: string) => {
        switch (type) {
            case 'CREDENTIAL': return <Lock className="h-4 w-4 text-amber-400" />;
            case 'KEY': return <Key className="h-4 w-4 text-primary" />;
            case 'FILE': return <FileKey className="h-4 w-4 text-blue-400" />;
            case 'NOTE': return <Shield className="h-4 w-4 text-emerald-400" />;
            default: return <Lock className="h-4 w-4 text-slate-400" />;
        }
    };

    // Sub-tab state (Secrets vs Spray Tracker)
    const [subTab, setSubTab] = useState<'secrets' | 'spray'>('secrets');

    return (
        <>
            {/* Sub-tab switcher */}
            <div className="flex items-center gap-1 mb-5 bg-slate-900/50 border border-slate-800 rounded-lg p-1 w-fit">
                <button
                    className={cn(
                        'px-4 py-2 rounded-md text-xs font-semibold transition-colors flex items-center gap-2',
                        subTab === 'secrets'
                            ? 'bg-primary/15 text-primary'
                            : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                    )}
                    onClick={() => setSubTab('secrets')}
                >
                    <Lock className="h-3.5 w-3.5" /> Secrets
                </button>
                <button
                    className={cn(
                        'px-4 py-2 rounded-md text-xs font-semibold transition-colors flex items-center gap-2',
                        subTab === 'spray'
                            ? 'bg-primary/15 text-primary'
                            : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                    )}
                    onClick={() => setSubTab('spray')}
                >
                    <Target className="h-3.5 w-3.5" /> Spray Tracker
                </button>
            </div>

            {subTab === 'spray' ? (
                <SprayTracker engagementId={engagementId} />
            ) : (
            <>
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
                {/* Toolbar */}
                <div className="flex flex-col gap-3">
                    {/* Row 1: search + sort + view toggle */}
                    <div className="flex flex-col md:flex-row md:items-center gap-3">
                        <div className="relative flex-1 max-w-md">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search vault items..."
                                className="pl-10 bg-slate-900/50 border-slate-800 text-white h-10 w-full rounded-xl focus:ring-primary/20"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>
                        <div className="flex items-center gap-2">
                            {/* Sort */}
                            <Select value={sortBy} onValueChange={(v: any) => setSortBy(v)}>
                                <SelectTrigger className="h-9 w-36 bg-slate-900/50 border-slate-800 text-slate-300 text-xs rounded-lg">
                                    <ArrowUpDown className="h-3 w-3 mr-1.5 text-slate-500" />
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    <SelectItem value="date">Newest first</SelectItem>
                                    <SelectItem value="name">Name A–Z</SelectItem>
                                    <SelectItem value="type">By type</SelectItem>
                                </SelectContent>
                            </Select>
                            {/* View toggle */}
                            <div className="flex items-center bg-slate-900/50 border border-slate-800 rounded-lg p-1">
                                <button
                                    className={`px-2.5 py-1.5 rounded-md transition-colors ${
                                        viewMode === 'tile' ? 'bg-primary/15 text-primary' : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                                    }`}
                                    onClick={() => setView('tile')}
                                    title="Tile view"
                                >
                                    <LayoutGrid className="h-4 w-4" />
                                </button>
                                <button
                                    className={`px-2.5 py-1.5 rounded-md transition-colors ${
                                        viewMode === 'table' ? 'bg-primary/15 text-primary' : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
                                    }`}
                                    onClick={() => setView('table')}
                                    title="Table view"
                                >
                                    <List className="h-4 w-4" />
                                </button>
                            </div>
                        </div>
                        {/* Add button - far right */}
                        {canCreateVault && (
                            <Button
                                className="bg-primary hover:bg-primary/90 text-white rounded-xl shadow-lg shadow-primary/20 ml-auto flex-shrink-0"
                                onClick={() => setIsAddDialogOpen(true)}
                            >
                                <Plus className="h-4 w-4 mr-2" />
                                Add Secret Item
                            </Button>
                        )}
                    </div>
                    {/* Row 2: type filter chips */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                        {(['ALL', 'CREDENTIAL', 'KEY', 'FILE', 'NOTE'] as const).map(type => (
                            <button
                                key={type}
                                onClick={() => setFilterType(type)}
                                className={`px-3 py-1 rounded-full text-[11px] font-semibold border transition-colors ${
                                    filterType === type
                                        ? 'bg-primary/15 border-primary/40 text-primary'
                                        : 'bg-slate-900/50 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white'
                                }`}
                            >
                                {type === 'ALL' ? 'All' : type === 'CREDENTIAL' ? 'Credentials' : type === 'KEY' ? 'Keys' : type === 'FILE' ? 'Files' : 'Notes'}
                                {type !== 'ALL' && (
                                    <span className="ml-1.5 opacity-60">
                                        {items.filter(i => i.item_type === type).length}
                                    </span>
                                )}
                                {type === 'ALL' && <span className="ml-1.5 opacity-60">{items.length}</span>}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Add Item Dialog */}
                <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
                    <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[500px]">
                        <DialogHeader>
                            <DialogTitle>Add Vault Item</DialogTitle>
                            <DialogDescription className="text-slate-400">
                                Securely store credentials, keys, or sensitive notes.
                            </DialogDescription>
                        </DialogHeader>

                        <div className="space-y-4 py-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Item Name</Label>
                                    <Input
                                        value={newItem.name}
                                        onChange={(e) => setNewItem({ ...newItem, name: e.target.value })}
                                        placeholder="e.g. Domain Admin"
                                        className={`bg-slate-950/50 border-slate-800 ${!newItem.name.trim() ? 'border-red-500/50 focus:ring-red-500/20' : ''}`}
                                        required
                                    />
                                    {!newItem.name.trim() && (
                                        <p className="text-xs text-red-400">Required</p>
                                    )}
                                </div>
                                <div className="space-y-2">
                                    <Label>Type</Label>
                                    <Select
                                        value={newItem.item_type}
                                        onValueChange={(v: any) => setNewItem({ ...newItem, item_type: v })}
                                    >
                                        <SelectTrigger className="bg-slate-950/50 border-slate-800">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            <SelectItem value="CREDENTIAL">Credential</SelectItem>
                                            <SelectItem value="KEY">Encryption Key</SelectItem>
                                            <SelectItem value="FILE">Sensitive File</SelectItem>
                                            <SelectItem value="NOTE">Secure Note</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            {newItem.item_type === 'CREDENTIAL' && (
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Username</Label>
                                        <Input
                                            value={newItem.username}
                                            onChange={(e) => setNewItem({ ...newItem, username: e.target.value })}
                                            className="bg-slate-950/50 border-slate-800"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Password</Label>
                                        <Input
                                            type="password"
                                            value={newItem.password}
                                            onChange={(e) => setNewItem({ ...newItem, password: e.target.value })}
                                            className="bg-slate-950/50 border-slate-800"
                                        />
                                    </div>
                                </div>
                            )}

                            {newItem.item_type === 'KEY' && (
                                <div className="space-y-2">
                                    <Label>Private/Public Key</Label>
                                    <Textarea
                                        value={newItem.note}
                                        onChange={(e) => setNewItem({ ...newItem, note: e.target.value })}
                                        className="bg-slate-950/50 border-slate-800 font-mono text-xs h-32"
                                        placeholder="-----BEGIN RSA PRIVATE KEY-----"
                                    />
                                </div>
                            )}

                            {newItem.item_type === 'FILE' && (
                                <div className="space-y-2">
                                    <Label>Choose File</Label>
                                    <Input
                                        type="file"
                                        onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                                        className="bg-slate-950/50 border-slate-800"
                                    />
                                </div>
                            )}

                            {newItem.item_type === 'NOTE' && (
                                <div className="space-y-2">
                                    <Label>Secure Note</Label>
                                    <Textarea
                                        value={newItem.note}
                                        onChange={(e) => setNewItem({ ...newItem, note: e.target.value })}
                                        className="bg-slate-950/50 border-slate-800 h-32"
                                    />
                                </div>
                            )}

                            <div className="space-y-2">
                                <Label>Description (Public)</Label>
                                <Input
                                    value={newItem.description}
                                    onChange={(e) => setNewItem({ ...newItem, description: e.target.value })}
                                    placeholder="Brief context for the team"
                                    className="bg-slate-950/50 border-slate-800"
                                />
                            </div>
                        </div>

                        <DialogFooter>
                            <Button variant="ghost" onClick={() => setIsAddDialogOpen(false)} disabled={isSubmitting}>
                                Cancel
                            </Button>
                            <Button
                                className="bg-primary hover:bg-primary/90"
                                onClick={handleAddItem}
                                disabled={isSubmitting || !newItem.name.trim()}
                            >
                                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save to Vault'}
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* Edit Dialog */}
                    <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
                        <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[500px]">
                            <DialogHeader>
                                <DialogTitle>Edit Vault Item</DialogTitle>
                                <DialogDescription className="text-slate-400">
                                    Update the details of this sensitive item.
                                </DialogDescription>
                            </DialogHeader>

                            <div className="space-y-4 py-4">
                                <div className="space-y-2">
                                    <Label>Item Name</Label>
                                    <Input
                                        value={editForm.name}
                                        onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                                        className="bg-slate-950/50 border-slate-800"
                                    />
                                </div>

                                {editingItem?.item_type === 'CREDENTIAL' && (
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label>Username</Label>
                                            <Input
                                                value={editForm.username}
                                                onChange={(e) => setEditForm({ ...editForm, username: e.target.value })}
                                                className="bg-slate-950/50 border-slate-800"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Password</Label>
                                            <Input
                                                type="text"
                                                value={editForm.password}
                                                onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
                                                className="bg-slate-950/50 border-slate-800"
                                            />
                                        </div>
                                    </div>
                                )}

                                {(editingItem?.item_type === 'KEY' || editingItem?.item_type === 'NOTE') && (
                                    <div className="space-y-2">
                                        <Label>{editingItem.item_type === 'KEY' ? 'Key Content' : 'Secure Note'}</Label>
                                        <Textarea
                                            value={editForm.note}
                                            onChange={(e) => setEditForm({ ...editForm, note: e.target.value })}
                                            className="bg-slate-950/50 border-slate-800 font-mono text-xs h-32"
                                        />
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <Label>Description (Public)</Label>
                                    <Input
                                        value={editForm.description}
                                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                                        className="bg-slate-950/50 border-slate-800"
                                    />
                                </div>
                            </div>

                            <DialogFooter>
                                <Button variant="ghost" onClick={() => setIsEditDialogOpen(false)} disabled={isSubmitting}>
                                    Cancel
                                </Button>
                                <Button className="bg-primary hover:bg-primary/90" onClick={handleUpdateItem} disabled={isSubmitting}>
                                    {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Update Item'}
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>

                {/* Content List */}
                {isLoading ? (
                    <div className="flex justify-center py-20">
                        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
                    </div>
                ) : processedItems.length === 0 ? (
                    <div className="text-center py-20 bg-slate-900/20 border border-dashed border-slate-800 rounded-3xl">
                        <Shield className="h-16 w-16 mx-auto mb-4 text-slate-700 opacity-50" />
                        <h3 className="text-lg font-semibold text-slate-400">{items.length === 0 ? 'Vault is empty' : 'No items match filters'}</h3>
                        <p className="text-slate-500 text-sm mt-1">{items.length === 0 ? 'Start storing sensitive items for the team.' : 'Try adjusting your search or filter.'}</p>
                    </div>
                ) : viewMode === 'tile' ? (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {processedItems.map((item) => (
                            <VaultItemCard
                                key={item.id}
                                item={{ ...item, _noteCount: noteCountByVaultItem[item.id] || 0 }}
                                engagementId={engagementId}
                                getItemIcon={getItemIcon}
                                handleDeleteItem={handleDeleteItem}
                                togglePassword={togglePassword}
                                copyToClipboard={copyToClipboard}
                                revealedItems={revealedItems}
                                revealAndGet={revealAndGet}
                                copiedId={copiedId}
                                handleSecureDownload={handleSecureDownload}
                                onEdit={handleEditItem}
                                onLink={handleOpenLinkDialog}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="space-y-1.5">
                        {/* Table header */}
                        <div className="flex items-center gap-3 px-4 py-1.5 text-[10px] uppercase tracking-wider text-slate-600 font-bold">
                            <span className="w-48 flex-shrink-0">Name</span>
                            <span className="w-24 flex-shrink-0">Type</span>
                            <span className="flex-[2] min-w-0">Content / Username</span>
                            <span className="flex-[2] min-w-0">Password</span>
                            <span className="w-28 flex-shrink-0">Links</span>
                            <span className="w-40 flex-shrink-0">Created</span>
                            <span className="w-8 flex-shrink-0"></span>
                        </div>
                        {processedItems.map((item) => (
                            <VaultItemRow
                                key={item.id}
                                item={{ ...item, _noteCount: noteCountByVaultItem[item.id] || 0 }}
                                engagementId={engagementId}
                                getItemIcon={getItemIcon}
                                handleDeleteItem={handleDeleteItem}
                                togglePassword={togglePassword}
                                copyToClipboard={copyToClipboard}
                                revealedItems={revealedItems}
                                revealAndGet={revealAndGet}
                                copiedId={copiedId}
                                handleSecureDownload={handleSecureDownload}
                                onEdit={handleEditItem}
                                onLink={handleOpenLinkDialog}
                            />
                        ))}
                    </div>
                )}

                <div className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-4 flex gap-4">
                    <AlertCircle className="h-5 w-5 text-amber-500 shrink-0" />
                    <div>
                        <h4 className="text-sm font-bold text-amber-500">Security Warning</h4>
                        <p className="text-xs text-amber-500/70 mt-0.5">
                            Items in the vault are accessible to all operators assigned to this engagement.
                            Activity logs track who views or modifies these secrets.
                        </p>
                    </div>
                </div>
            </div>

            {/* Link Dialog — unified shared modal */}
            {linkingItem && (
                <LinkEntityDialog
                    open={isLinkDialogOpen}
                    onOpenChange={setIsLinkDialogOpen}
                    engagementId={engagementId}
                    entityType="vault"
                    entityId={linkingItem.id}
                    entityName={linkingItem.name}
                    linkedIds={linkingItemLinkedIds}
                    onLink={handleEntityLink}
                    onUnlink={handleEntityUnlink}
                />
            )}

            <ConfirmDialog />
        </>
        )}
        </>
    );
}

const Separator = ({ className }: { className?: string }) => (
    <div className={cn("h-px w-full", className)} />
);
