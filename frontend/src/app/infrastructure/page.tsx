/**
 * infrastructure/page.tsx — Infrastructure Registry Page
 *
 * Paginated, filterable card grid of red-team infrastructure items (VPS,
 * C2 servers, redirectors, proxies, jumpboxes, phishing hosts, etc.).
 *
 * Features:
 *  - Search by name, IP, or hostname with type and status dropdown filters.
 *  - `InfraCard` component: shows name, type badge (colour-coded), status
 *    badge (active/standby/decommissioned), IP, provider, and location.
 *  - `InfraDetailDialog`: read-only modal with all fields in a 2-column
 *    grid, notes section, linked entities (findings, test cases, notes)
 *    with inline unlink, and timestamps.
 *  - Create dialog: full form (name, type, status, IPs, hostname, provider,
 *    region, OS, point-of-presence, notes).
 *  - Permission-gated create/delete actions.
 *  - Pagination controls at the bottom (50 items per page).
 */
'use client';

import { useState } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import api, { apiErrorMessage } from '@/lib/api';
import { useAuthStore } from '@/stores/auth-store';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { FileDropzone, SelectedFileCard } from '@/components/ui/file-dropzone';
import { MAX_VAULT_FILE_BYTES } from '@/lib/upload-limits';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Server,
    Plus,
    Search,
    Loader2,
    Trash2,
    MapPin,
    Wifi,
    Globe,
    Monitor,
    ChevronLeft,
    ChevronRight,
    Link2,
    Edit,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    useInfraItems,
    useInfraItem,
    useCreateInfraItem,
    useUpdateInfraItem,
    useDeleteInfraItem,
    useUnlinkInfra,
    type InfraItem,
    type InfraItemDetail,
    type InfraType,
    type InfraStatus,
} from '@/lib/hooks/use-infra';
import { useGlobalPermission } from '@/lib/hooks/use-permissions';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { cn } from '@/lib/utils';

// ── Constants ───────────────────────────────────────────────────

// Fallback colors for infra types when DB has a hex color
const typeColorMap: Record<string, string> = {
    VPS: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    C2: 'bg-red-500/10 text-red-400 border-red-500/30',
    REDIRECTOR: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    PROXY: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    PHISHING: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
    JUMPBOX: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};
const defaultTypeColor = 'bg-slate-500/10 text-slate-400 border-slate-500/30';

const STATUS_OPTIONS: { value: InfraStatus; label: string; color: string; dot: string }[] = [
    { value: 'ACTIVE', label: 'Active', color: 'bg-emerald-500/10 text-emerald-400', dot: 'bg-emerald-400' },
    { value: 'STANDBY', label: 'Standby', color: 'bg-amber-500/10 text-amber-400', dot: 'bg-amber-400' },
    { value: 'DECOMMISSIONED', label: 'Decommissioned', color: 'bg-slate-500/10 text-slate-500', dot: 'bg-slate-500' },
];

const getTypeColor = (t: string) => typeColorMap[t] || defaultTypeColor;
const getStatusConfig = (s: string) => STATUS_OPTIONS.find(x => x.value === s) || STATUS_OPTIONS[0];

const formatTimeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
};

// ── Infra Card ──────────────────────────────────────────────────

function InfraCard({ item, onView, onDelete, canDelete }: {
    item: InfraItem;
    onView: () => void;
    onDelete: () => void;
    canDelete: boolean;
}) {
    const typeColor = getTypeColor(item.infra_type);
    const statusConf = getStatusConfig(item.status);

    return (
        <Card
            className="border-slate-800 bg-slate-900/50 hover:bg-slate-900/80 hover:border-slate-700 transition-all cursor-pointer group"
            onClick={onView}
        >
            <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0 flex-1">
                        <div className="p-2 rounded-lg bg-teal-500/10 border border-teal-500/20 shrink-0">
                            <Server className="h-4 w-4 text-teal-400" />
                        </div>
                        <div className="min-w-0 flex-1">
                            <h3 className="text-sm font-bold text-white truncate" title={item.name}>{item.name}</h3>
                            <div className="flex items-center gap-2 mt-1 flex-wrap">
                                <Badge className={cn('text-[10px] px-1.5 py-0 border-none', typeColor)}>
                                    {item.infra_type}
                                </Badge>
                                <Badge className={cn('text-[10px] px-1.5 py-0 border-none flex items-center gap-1', statusConf.color)}>
                                    <span className={cn('h-1.5 w-1.5 rounded-full', statusConf.dot)} />
                                    {statusConf.label}
                                </Badge>
                            </div>
                            <div className="flex items-center gap-3 mt-2 text-xs text-slate-500 flex-wrap">
                                {item.ip_address && (
                                    <span className="flex items-center gap-1 font-mono">
                                        <Wifi className="h-3 w-3" />
                                        {item.ip_address}
                                    </span>
                                )}
                                {item.provider && (
                                    <span className="flex items-center gap-1">
                                        <Globe className="h-3 w-3" />
                                        {item.provider}
                                    </span>
                                )}
                                {item.point_of_presence && (
                                    <span className="flex items-center gap-1">
                                        <MapPin className="h-3 w-3" />
                                        {item.point_of_presence}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                    {canDelete && (
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-slate-700 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                            onClick={e => { e.stopPropagation(); onDelete(); }}
                        >
                            <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

// ── Imports added for vault ─────────────────────────────────────
import {
    useInfraVault,
    useInfraVaultAccessCheck,
    useInfraVaultAccessList,
    useCreateInfraVaultItem,
    useUploadInfraVaultFile,
    useUpdateInfraVaultItem,
    useDeleteInfraVaultItem,
    useGrantInfraVaultAccess,
    useRevokeInfraVaultAccess,
    useCheckPassword,
    type InfraVaultItem as IVaultItem,
} from '@/lib/hooks/use-infra-vault';
import { useUsers } from '@/lib/hooks/use-users';
import {
    Lock, Key, Shield, FileText, Eye, EyeOff, Copy, Download, ShieldCheck, UserPlus, X, ChevronDown, ChevronUp,
    AlertTriangle, Save, Pencil,
} from 'lucide-react';
import { Separator } from '@/components/ui/separator';

// Bloom filter password warning component
function PasswordWarning({ password }: { password: string }) {
    const { data } = useCheckPassword(password);
    if (!data?.found) return null;
    return (
        <div className="flex items-center gap-1.5 mt-1 text-[10px] text-red-400 animate-in fade-in">
            <AlertTriangle className="h-3 w-3 shrink-0" />
            <span>This password was found in an uploaded wordlist — consider using a stronger one.</span>
        </div>
    );
}

const VAULT_TYPE_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
    CREDENTIAL: { icon: Lock, label: 'Credential', color: 'text-amber-400' },
    KEY: { icon: Key, label: 'SSH Key / Secret', color: 'text-purple-400' },
    NOTE: { icon: Shield, label: 'Secure Note', color: 'text-emerald-400' },
    FILE: { icon: FileText, label: 'File', color: 'text-cyan-400' },
};

// ── Detail Dialog ───────────────────────────────────────────────

function InfraDetailDialog({ itemId, onClose }: { itemId: string; onClose: () => void }) {
    const { data: item, isLoading } = useInfraItem(itemId);
    const unlinkInfra = useUnlinkInfra();

    // Vault state
    const { data: accessCheck } = useInfraVaultAccessCheck(itemId);
    const { data: vaultItems = [], isLoading: vaultLoading } = useInfraVault(itemId);
    const { data: vaultAccess = [] } = useInfraVaultAccessList(itemId);
    const { data: allUsers = [] } = useUsers();
    const createVault = useCreateInfraVaultItem();
    const uploadVaultFile = useUploadInfraVaultFile();
    const deleteVault = useDeleteInfraVaultItem();
    const grantAccess = useGrantInfraVaultAccess();
    const revokeAccess = useRevokeInfraVaultAccess();
    const { confirm, ConfirmDialog: VaultConfirm } = useConfirmDialog();

    const updateVault = useUpdateInfraVaultItem();

    const [vaultOpen, setVaultOpen] = useState(true);
    const [accessOpen, setAccessOpen] = useState(false);
    const [addVaultOpen, setAddVaultOpen] = useState(false);
    const [revealedPasswords, setRevealedPasswords] = useState<Set<string>>(new Set());
    const [newVault, setNewVault] = useState({ name: '', item_type: 'CREDENTIAL', username: '', password: '', note: '', description: '' });
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editForm, setEditForm] = useState({ name: '', username: '', password: '', note: '', description: '' });

    const hasAccess = accessCheck?.has_access ?? false;
    const canManage = accessCheck?.can_manage ?? false;
    // Only admins/team-leads may delegate ACL management to others
    // (backend gate at infra.py:grant_vault_access; GHSA-58q3-f33p-w84m).
    const { user } = useAuthStore();
    const canDelegateManage = user?.role === 'admin' || user?.role === 'team_lead';
    const [grantAsManager, setGrantAsManager] = useState(false);

    const toggleReveal = (id: string) => {
        setRevealedPasswords(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const copyToClipboard = (text: string, label: string) => {
        navigator.clipboard.writeText(text);
        toast.success(`${label} copied`);
    };

    const handleAddVault = async () => {
        if (!newVault.name) { toast.error('Name is required'); return; }
        try {
            if (newVault.item_type === 'FILE' && selectedFile) {
                await uploadVaultFile.mutateAsync({
                    infraItemId: itemId,
                    name: newVault.name,
                    description: newVault.description || undefined,
                    file: selectedFile,
                });
            } else {
                await createVault.mutateAsync({
                    infraItemId: itemId,
                    name: newVault.name,
                    item_type: newVault.item_type,
                    username: newVault.username || undefined,
                    password: newVault.password || undefined,
                    note: newVault.note || undefined,
                    description: newVault.description || undefined,
                });
            }
            toast.success('Vault item added');
            setAddVaultOpen(false);
            setNewVault({ name: '', item_type: 'CREDENTIAL', username: '', password: '', note: '', description: '' });
            setSelectedFile(null);
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to add vault item'));
        }
    };

    const handleDeleteVault = async (vi: IVaultItem) => {
        const ok = await confirm({ title: 'Delete Vault Item', description: `Delete "${vi.name}"? This cannot be undone.`, confirmLabel: 'Delete', variant: 'destructive' });
        if (!ok) return;
        try {
            await deleteVault.mutateAsync({ infraItemId: itemId, vaultId: vi.id });
            toast.success('Deleted');
        } catch { toast.error('Failed to delete'); }
    };

    const handleDownload = async (vi: IVaultItem) => {
        try {
            const resp = await api.get(`/infra/items/${itemId}/vault/${vi.id}/download`, { responseType: 'blob' });
            const url = URL.createObjectURL(resp.data);
            const a = document.createElement('a');
            a.href = url;
            a.download = vi.filename || 'file';
            a.click();
            URL.revokeObjectURL(url);
        } catch { toast.error('Download failed'); }
    };

    const startEditing = (vi: IVaultItem) => {
        setEditingId(vi.id);
        setEditForm({ name: vi.name, username: vi.username || '', password: vi.password || '', note: vi.note || '', description: vi.description || '' });
    };

    const handleSaveEdit = async () => {
        if (!editingId) return;
        try {
            await updateVault.mutateAsync({
                infraItemId: itemId,
                vaultId: editingId,
                name: editForm.name,
                username: editForm.username || undefined,
                password: editForm.password || undefined,
                note: editForm.note || undefined,
                description: editForm.description || undefined,
            });
            toast.success('Credential updated');
            setEditingId(null);
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to update'));
        }
    };

    if (!item && isLoading) {
        return (
            <Dialog open onOpenChange={() => onClose()}>
                <DialogContent className="bg-slate-900 border-slate-700 text-white">
                    <DialogHeader><DialogTitle className="sr-only">Loading</DialogTitle></DialogHeader>
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                </DialogContent>
            </Dialog>
        );
    }

    if (!item) return null;

    const typeColor = getTypeColor(item.infra_type);
    const statusConf = getStatusConfig(item.status);
    const allLinked = [...(item.linked_findings || []), ...(item.linked_testcases || []), ...(item.linked_notes || [])];

    const fields = [
        { label: 'IP Address', value: item.ip_address, icon: Wifi },
        { label: 'Internal IP', value: item.internal_ip, icon: Wifi },
        { label: 'Hostname', value: item.hostname, icon: Globe },
        { label: 'Provider', value: item.provider, icon: Globe },
        { label: 'Region', value: item.region, icon: MapPin },
        { label: 'OS', value: item.os, icon: Monitor },
        { label: 'Point of Presence', value: item.point_of_presence, icon: MapPin },
    ].filter(f => f.value);

    // Users not yet granted access (for the grant dropdown)
    const grantableUsers = allUsers.filter(
        (u: any) => !vaultAccess.some(a => a.user_id === u.id)
    );

    return (
        <Dialog open onOpenChange={() => onClose()}>
            <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-2xl max-h-[85vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Server className="h-5 w-5 text-teal-400" />
                        <span className="truncate" title={item.name}>{item.name}</span>
                    </DialogTitle>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Badge className={cn('text-[10px] px-1.5 py-0 border-none', typeColor)}>
                            {item.infra_type}
                        </Badge>
                        <Badge className={cn('text-[10px] px-1.5 py-0 border-none flex items-center gap-1', statusConf.color)}>
                            <span className={cn('h-1.5 w-1.5 rounded-full', statusConf.dot)} />
                            {statusConf.label}
                        </Badge>
                    </div>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto space-y-4 min-h-0">
                    {/* Fields Grid */}
                    {fields.length > 0 && (
                        <div className="grid grid-cols-2 gap-3">
                            {fields.map(f => {
                                const Icon = f.icon;
                                return (
                                    <div key={f.label} className="bg-slate-950/50 rounded-lg border border-slate-800 p-3">
                                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                                            <Icon className="h-3 w-3" />
                                            {f.label}
                                        </div>
                                        <div className="text-sm text-white font-mono">{f.value}</div>
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {/* Notes */}
                    {item.notes && (
                        <div className="space-y-1">
                            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Notes</h4>
                            <div className="text-sm text-slate-300 whitespace-pre-wrap bg-slate-950/50 rounded-lg border border-slate-800 p-3">
                                {item.notes}
                            </div>
                        </div>
                    )}

                    <Separator className="bg-slate-800/60" />

                    {/* ═══════════ CREDENTIALS VAULT ═══════════ */}
                    <div>
                        <button
                            onClick={() => setVaultOpen(!vaultOpen)}
                            className="flex items-center justify-between w-full text-left group"
                        >
                            <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                                <ShieldCheck className="h-4 w-4 text-amber-400" />
                                Credentials Vault
                                <span className="text-xs text-slate-500">({vaultItems.length})</span>
                            </h4>
                            {vaultOpen ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                        </button>

                        {vaultOpen && (
                            <div className="mt-3 space-y-2">
                                {!hasAccess ? (
                                    <div className="flex items-center gap-3 py-6 justify-center text-slate-500 bg-slate-950/50 rounded-lg border border-slate-800">
                                        <Lock className="h-5 w-5" />
                                        <div className="text-sm">
                                            <p className="font-medium text-slate-400">Access Restricted</p>
                                            <p className="text-xs">Ask an admin to grant you vault access for this item.</p>
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        {/* Vault Items */}
                                        {vaultLoading ? (
                                            <div className="flex items-center justify-center py-4">
                                                <Loader2 className="h-5 w-5 animate-spin text-amber-400" />
                                            </div>
                                        ) : vaultItems.length === 0 ? (
                                            <p className="text-xs text-slate-500 italic py-3 text-center border border-dashed border-slate-800 rounded-lg">
                                                No credentials stored yet.
                                            </p>
                                        ) : (
                                            <div className="space-y-2">
                                                {vaultItems.map(vi => {
                                                    const conf = VAULT_TYPE_CONFIG[vi.item_type] || VAULT_TYPE_CONFIG.NOTE;
                                                    const VIcon = conf.icon;
                                                    const isRevealed = revealedPasswords.has(vi.id);
                                                    return (
                                                        <div key={vi.id} className="bg-slate-950/50 rounded-lg border border-slate-800 p-3 group">
                                                            {editingId === vi.id ? (
                                                                /* ── Edit Mode (type-specific) ── */
                                                                <div className="space-y-2">
                                                                    <div className="flex items-center gap-2">
                                                                        <VIcon className={cn('h-4 w-4 shrink-0', conf.color)} />
                                                                        <span className="text-[10px] text-slate-500">{conf.label}</span>
                                                                    </div>
                                                                    <Input
                                                                        value={editForm.name}
                                                                        onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                                                                        placeholder="Name *"
                                                                        className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                    />

                                                                    {vi.item_type === 'CREDENTIAL' && (
                                                                        <>
                                                                            <Input
                                                                                value={editForm.username}
                                                                                onChange={e => setEditForm(f => ({ ...f, username: e.target.value }))}
                                                                                placeholder="Username"
                                                                                className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                            />
                                                                            <Input
                                                                                value={editForm.password}
                                                                                onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))}
                                                                                placeholder="Password"
                                                                                className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                            />
                                                                            {editForm.password && <PasswordWarning password={editForm.password} />}
                                                                        </>
                                                                    )}

                                                                    {vi.item_type === 'KEY' && (
                                                                        <>
                                                                            <Input
                                                                                value={editForm.username}
                                                                                onChange={e => setEditForm(f => ({ ...f, username: e.target.value }))}
                                                                                placeholder="Username (e.g. root, deploy)"
                                                                                className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                            />
                                                                            <div>
                                                                                <label className="text-[10px] text-slate-500 mb-1 block">Private Key</label>
                                                                                <Textarea
                                                                                    value={editForm.password}
                                                                                    onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))}
                                                                                    placeholder={'-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----'}
                                                                                    className="min-h-[120px] text-xs font-mono bg-slate-900 border-slate-700 text-green-400 leading-relaxed"
                                                                                />
                                                                            </div>
                                                                            <Input
                                                                                value={editForm.note}
                                                                                onChange={e => setEditForm(f => ({ ...f, note: e.target.value }))}
                                                                                placeholder="Passphrase (optional)"
                                                                                className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                            />
                                                                        </>
                                                                    )}

                                                                    {vi.item_type === 'NOTE' && (
                                                                        <Textarea
                                                                            value={editForm.note}
                                                                            onChange={e => setEditForm(f => ({ ...f, note: e.target.value }))}
                                                                            placeholder="Secure note content"
                                                                            className="min-h-[100px] text-xs bg-slate-900 border-slate-700 text-white"
                                                                        />
                                                                    )}

                                                                    <Input
                                                                        value={editForm.description}
                                                                        onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                                                                        placeholder="Description (optional)"
                                                                        className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                    />
                                                                    <div className="flex gap-2 justify-end">
                                                                        <Button size="sm" variant="outline" className="h-7 text-xs border-slate-700 text-slate-400" onClick={() => setEditingId(null)}>
                                                                            Cancel
                                                                        </Button>
                                                                        <Button
                                                                            size="sm"
                                                                            className="h-7 text-xs bg-primary hover:bg-primary/90 text-white"
                                                                            disabled={updateVault.isPending}
                                                                            onClick={handleSaveEdit}
                                                                        >
                                                                            {updateVault.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Save className="h-3 w-3 mr-1" />}
                                                                            Save
                                                                        </Button>
                                                                    </div>
                                                                </div>
                                                            ) : (
                                                                /* ── View Mode (type-specific) ── */
                                                                <>
                                                            <div className="flex items-start justify-between gap-2">
                                                                <div className="flex items-center gap-2 min-w-0">
                                                                    <VIcon className={cn('h-4 w-4 shrink-0', conf.color)} />
                                                                    <div className="min-w-0">
                                                                        <span className="text-sm font-bold text-white truncate block">{vi.name}</span>
                                                                        <span className="text-[10px] text-slate-500">{conf.label}</span>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                                                    {vi.item_type === 'FILE' && (
                                                                        <button onClick={() => handleDownload(vi)} className="p-1 text-slate-500 hover:text-cyan-400 transition-colors" title="Download">
                                                                            <Download className="h-3.5 w-3.5" />
                                                                        </button>
                                                                    )}
                                                                    {canManage && vi.item_type !== 'FILE' && (
                                                                        <button onClick={() => startEditing(vi)} className="p-1 text-slate-600 hover:text-amber-400 transition-colors" title="Edit">
                                                                            <Pencil className="h-3.5 w-3.5" />
                                                                        </button>
                                                                    )}
                                                                    {canManage && (
                                                                        <button onClick={() => handleDeleteVault(vi)} className="p-1 text-slate-600 hover:text-red-400 transition-colors" title="Delete">
                                                                            <Trash2 className="h-3.5 w-3.5" />
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>

                                                            {/* ─ CREDENTIAL view ─ */}
                                                            {vi.item_type === 'CREDENTIAL' && (
                                                                <>
                                                                    {vi.username && (
                                                                        <div className="mt-2 flex items-center gap-2 text-xs">
                                                                            <span className="text-slate-500 w-16 shrink-0">User</span>
                                                                            <code className="text-slate-300 font-mono bg-slate-900 px-2 py-0.5 rounded flex-1 truncate">{vi.username}</code>
                                                                            <button onClick={() => copyToClipboard(vi.username!, 'Username')} className="p-1 text-slate-600 hover:text-white">
                                                                                <Copy className="h-3 w-3" />
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                    {vi.password && (
                                                                        <div className="mt-1 flex items-center gap-2 text-xs">
                                                                            <span className="text-slate-500 w-16 shrink-0">Pass</span>
                                                                            <code className="text-slate-300 font-mono bg-slate-900 px-2 py-0.5 rounded flex-1 truncate">
                                                                                {isRevealed ? vi.password : '•'.repeat(Math.min(vi.password.length, 20))}
                                                                            </code>
                                                                            <button onClick={() => toggleReveal(vi.id)} className="p-1 text-slate-600 hover:text-white">
                                                                                {isRevealed ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                                                            </button>
                                                                            <button onClick={() => copyToClipboard(vi.password!, 'Password')} className="p-1 text-slate-600 hover:text-white">
                                                                                <Copy className="h-3 w-3" />
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                </>
                                                            )}

                                                            {/* ─ KEY view ─ */}
                                                            {vi.item_type === 'KEY' && (
                                                                <>
                                                                    {vi.username && (
                                                                        <div className="mt-2 flex items-center gap-2 text-xs">
                                                                            <span className="text-slate-500 w-16 shrink-0">User</span>
                                                                            <code className="text-slate-300 font-mono bg-slate-900 px-2 py-0.5 rounded flex-1 truncate">{vi.username}</code>
                                                                            <button onClick={() => copyToClipboard(vi.username!, 'Username')} className="p-1 text-slate-600 hover:text-white">
                                                                                <Copy className="h-3 w-3" />
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                    {vi.password && (
                                                                        <div className="mt-2">
                                                                            <div className="flex items-center justify-between mb-1">
                                                                                <span className="text-[10px] text-slate-500">Private Key</span>
                                                                                <div className="flex items-center gap-1">
                                                                                    <button onClick={() => toggleReveal(vi.id)} className="p-1 text-slate-600 hover:text-white" title={isRevealed ? 'Hide' : 'Show'}>
                                                                                        {isRevealed ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                                                                    </button>
                                                                                    <button onClick={() => copyToClipboard(vi.password!, 'Key')} className="p-1 text-slate-600 hover:text-white" title="Copy">
                                                                                        <Copy className="h-3 w-3" />
                                                                                    </button>
                                                                                </div>
                                                                            </div>
                                                                            {isRevealed ? (
                                                                                <pre className="text-[10px] font-mono text-green-400 bg-slate-900 border border-slate-800 rounded-lg p-2 overflow-x-auto max-h-[200px] overflow-y-auto whitespace-pre leading-relaxed">
                                                                                    {vi.password}
                                                                                </pre>
                                                                            ) : (
                                                                                <div className="text-xs text-slate-500 bg-slate-900 border border-slate-800 rounded-lg p-2 font-mono">
                                                                                    •••••• ({vi.password.length} chars)
                                                                                </div>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                    {vi.note && (
                                                                        <div className="mt-1 flex items-center gap-2 text-xs">
                                                                            <span className="text-slate-500 w-16 shrink-0">Phrase</span>
                                                                            <code className="text-slate-300 font-mono bg-slate-900 px-2 py-0.5 rounded flex-1 truncate">
                                                                                {isRevealed ? vi.note : '•'.repeat(Math.min(vi.note.length, 12))}
                                                                            </code>
                                                                            <button onClick={() => copyToClipboard(vi.note!, 'Passphrase')} className="p-1 text-slate-600 hover:text-white">
                                                                                <Copy className="h-3 w-3" />
                                                                            </button>
                                                                        </div>
                                                                    )}
                                                                </>
                                                            )}

                                                            {/* ─ NOTE view ─ */}
                                                            {vi.item_type === 'NOTE' && vi.note && (
                                                                <div className="mt-2 text-xs text-slate-300 whitespace-pre-wrap bg-slate-900/50 p-2 rounded border border-slate-800">{vi.note}</div>
                                                            )}

                                                            {/* ─ FILE view ─ */}
                                                            {vi.item_type === 'FILE' && vi.filename && (
                                                                <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                                                                    <FileText className="h-3 w-3" />
                                                                    <span className="font-mono truncate">{vi.filename}</span>
                                                                </div>
                                                            )}

                                                            {vi.description && (
                                                                <p className="mt-1.5 text-[10px] text-slate-500 italic">{vi.description}</p>
                                                            )}
                                                                </>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}

                                        {/* Add vault item form */}
                                        {canManage && (
                                            <>
                                                {addVaultOpen ? (
                                                    <div className="bg-slate-950/50 rounded-lg border border-amber-500/20 p-3 space-y-2">
                                                        <div className="flex gap-2">
                                                            <Input
                                                                value={newVault.name}
                                                                onChange={e => setNewVault(v => ({ ...v, name: e.target.value }))}
                                                                placeholder="Name *"
                                                                className="flex-1 h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                            />
                                                            <Select value={newVault.item_type} onValueChange={v => setNewVault(nv => ({ ...nv, item_type: v }))}>
                                                                <SelectTrigger className="w-32 h-8 text-xs bg-slate-900 border-slate-700 text-white">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    <SelectItem value="CREDENTIAL">Credential</SelectItem>
                                                                    <SelectItem value="KEY">SSH Key / Secret</SelectItem>
                                                                    <SelectItem value="NOTE">Secure Note</SelectItem>
                                                                    <SelectItem value="FILE">File</SelectItem>
                                                                </SelectContent>
                                                            </Select>
                                                        </div>
                                                        {/* ─ Type-specific add fields ─ */}
                                                        {newVault.item_type === 'CREDENTIAL' && (
                                                            <>
                                                                <Input
                                                                    value={newVault.username}
                                                                    onChange={e => setNewVault(v => ({ ...v, username: e.target.value }))}
                                                                    placeholder="Username"
                                                                    className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                />
                                                                <Input
                                                                    type="password"
                                                                    value={newVault.password}
                                                                    onChange={e => setNewVault(v => ({ ...v, password: e.target.value }))}
                                                                    placeholder="Password"
                                                                    className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                />
                                                                {newVault.password && <PasswordWarning password={newVault.password} />}
                                                                <Textarea
                                                                    value={newVault.note}
                                                                    onChange={e => setNewVault(v => ({ ...v, note: e.target.value }))}
                                                                    placeholder="Notes (optional)"
                                                                    className="min-h-[50px] text-xs bg-slate-900 border-slate-700 text-white"
                                                                />
                                                            </>
                                                        )}

                                                        {newVault.item_type === 'KEY' && (
                                                            <>
                                                                <Input
                                                                    value={newVault.username}
                                                                    onChange={e => setNewVault(v => ({ ...v, username: e.target.value }))}
                                                                    placeholder="Username (e.g. root, deploy)"
                                                                    className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                />
                                                                <div>
                                                                    <label className="text-[10px] text-slate-500 mb-1 block">Private Key</label>
                                                                    <Textarea
                                                                        value={newVault.password}
                                                                        onChange={e => setNewVault(v => ({ ...v, password: e.target.value }))}
                                                                        placeholder={'-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----'}
                                                                        className="min-h-[120px] text-xs font-mono bg-slate-900 border-slate-700 text-green-400 leading-relaxed"
                                                                    />
                                                                </div>
                                                                <Input
                                                                    value={newVault.note}
                                                                    onChange={e => setNewVault(v => ({ ...v, note: e.target.value }))}
                                                                    placeholder="Passphrase (optional)"
                                                                    className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                                />
                                                            </>
                                                        )}

                                                        {newVault.item_type === 'NOTE' && (
                                                            <Textarea
                                                                value={newVault.note}
                                                                onChange={e => setNewVault(v => ({ ...v, note: e.target.value }))}
                                                                placeholder="Secure note content"
                                                                className="min-h-[100px] text-xs bg-slate-900 border-slate-700 text-white"
                                                            />
                                                        )}
                                                        {newVault.item_type === 'FILE' && (
                                                            !selectedFile ? (
                                                                <FileDropzone
                                                                    onFiles={files => setSelectedFile(files[0])}
                                                                    maxSizeBytes={MAX_VAULT_FILE_BYTES}
                                                                    compact
                                                                    hint="Keys, certs, or configs"
                                                                />
                                                            ) : (
                                                                <SelectedFileCard
                                                                    file={selectedFile}
                                                                    onRemove={() => setSelectedFile(null)}
                                                                />
                                                            )
                                                        )}
                                                        <Input
                                                            value={newVault.description}
                                                            onChange={e => setNewVault(v => ({ ...v, description: e.target.value }))}
                                                            placeholder="Description (optional)"
                                                            className="h-8 text-xs bg-slate-900 border-slate-700 text-white"
                                                        />
                                                        <div className="flex gap-2 justify-end">
                                                            <Button size="sm" variant="outline" className="h-7 text-xs border-slate-700 text-slate-400" onClick={() => { setAddVaultOpen(false); setSelectedFile(null); }}>
                                                                Cancel
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                className="h-7 text-xs bg-primary hover:bg-primary/90 text-white"
                                                                disabled={createVault.isPending || uploadVaultFile.isPending}
                                                                onClick={handleAddVault}
                                                            >
                                                                {(createVault.isPending || uploadVaultFile.isPending) ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Plus className="h-3 w-3 mr-1" />}
                                                                Add
                                                            </Button>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            onClick={() => setAddVaultOpen(true)}
                                                            className="text-[10px] text-amber-400 hover:text-amber-300 transition-colors flex items-center gap-0.5"
                                                        >
                                                            <Plus className="h-3 w-3" /> Add Credential
                                                        </button>
                                                        <button
                                                            onClick={() => setAccessOpen(!accessOpen)}
                                                            className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-0.5 ml-auto"
                                                        >
                                                            <UserPlus className="h-3 w-3" /> Manage Access
                                                        </button>
                                                    </div>
                                                )}
                                            </>
                                        )}

                                        {/* Access management */}
                                        {accessOpen && canManage && (
                                            <div className="bg-slate-950/50 rounded-lg border border-slate-800 p-3 space-y-2">
                                                <h5 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Vault Access</h5>
                                                {vaultAccess.length === 0 ? (
                                                    <p className="text-xs text-slate-500 italic">Only admins/team leads have access.</p>
                                                ) : (
                                                    <div className="space-y-1">
                                                        {vaultAccess.map(a => (
                                                            <div key={a.user_id} className="flex items-center justify-between text-xs bg-slate-900/50 rounded p-2">
                                                                <span className="text-slate-300 flex items-center gap-1.5">
                                                                    {a.display_name || a.username}
                                                                    {a.can_manage && (
                                                                        <Badge className="text-[9px] py-0 px-1 bg-amber-500/15 text-amber-400 border-amber-500/30">
                                                                            Manager
                                                                        </Badge>
                                                                    )}
                                                                </span>
                                                                <button
                                                                    onClick={async () => {
                                                                        try {
                                                                            await revokeAccess.mutateAsync({ infraItemId: itemId, userId: a.user_id });
                                                                            toast.success('Access revoked');
                                                                        } catch (err: any) {
                                                                            toast.error(apiErrorMessage(err, 'Failed to revoke access'));
                                                                        }
                                                                    }}
                                                                    className="text-slate-600 hover:text-red-400 transition-colors"
                                                                >
                                                                    <X className="h-3 w-3" />
                                                                </button>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                                {grantableUsers.length > 0 && (
                                                    <div className="space-y-1.5">
                                                        {canDelegateManage && (
                                                            <label className="flex items-center gap-1.5 text-[10px] text-slate-400 cursor-pointer">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={grantAsManager}
                                                                    onChange={(e) => setGrantAsManager(e.target.checked)}
                                                                    className="h-3 w-3 rounded bg-slate-900 border-slate-700"
                                                                />
                                                                Grant as manager (can also grant/revoke view-only access on this item)
                                                            </label>
                                                        )}
                                                        <Select onValueChange={async (userId) => {
                                                            try {
                                                                await grantAccess.mutateAsync({ infraItemId: itemId, userId, canManage: grantAsManager });
                                                                toast.success(grantAsManager ? 'Granted with manage' : 'Access granted');
                                                                setGrantAsManager(false);
                                                            } catch (err: any) {
                                                                toast.error(apiErrorMessage(err, 'Failed to grant access'));
                                                            }
                                                        }}>
                                                            <SelectTrigger className="h-8 text-xs bg-slate-900 border-slate-700 text-white">
                                                                <SelectValue placeholder="Grant access to..." />
                                                            </SelectTrigger>
                                                            <SelectContent>
                                                                {grantableUsers.map((u: any) => (
                                                                    <SelectItem key={u.id} value={u.id}>
                                                                        {u.display_name || u.username} <span className="text-slate-500 ml-1">@{u.username}</span>
                                                                    </SelectItem>
                                                                ))}
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        )}
                    </div>

                    <Separator className="bg-slate-800/60" />

                    {/* Linked Entities */}
                    <div className="space-y-2">
                        <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                            <Link2 className="h-4 w-4 text-primary" />
                            Linked Entities
                            <span className="text-xs text-slate-500">({allLinked.length})</span>
                        </h4>
                        {allLinked.length === 0 ? (
                            <p className="text-xs text-slate-500 italic py-2">No linked findings, test cases, or notes yet.</p>
                        ) : (
                            <div className="space-y-1">
                                {allLinked.map(entity => (
                                    <div key={`${entity.type}-${entity.id}`} className="flex items-center justify-between rounded-lg bg-slate-950/50 border border-slate-800 px-3 py-2 min-w-0">
                                        <div className="flex items-center gap-2 min-w-0 flex-1">
                                            <Badge className="text-[10px] py-0 bg-slate-800 text-slate-400 border-slate-700 capitalize shrink-0">
                                                {entity.type}
                                            </Badge>
                                            <span className="text-sm text-slate-300 truncate">{entity.title}</span>
                                        </div>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-6 w-6 text-slate-600 hover:text-red-400 shrink-0"
                                            onClick={async () => {
                                                await unlinkInfra.mutateAsync({ itemId, entityType: entity.type, entityId: entity.id });
                                                toast.success('Unlinked');
                                            }}
                                        >
                                            <Trash2 className="h-3 w-3" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-4 text-xs text-slate-500 border-t border-slate-800 pt-3">
                        <span>Created {formatTimeAgo(item.created_at)}</span>
                        <span>Updated {formatTimeAgo(item.updated_at)}</span>
                    </div>
                </div>
            </DialogContent>
            <VaultConfirm />
        </Dialog>
    );
}

// ── Main Page ───────────────────────────────────────────────────

const emptyForm = {
    name: '', infra_type: 'OTHER', status: 'ACTIVE',
    ip_address: '', internal_ip: '', hostname: '', provider: '',
    region: '', os: '', point_of_presence: '', notes: '',
};

export default function InfrastructurePage() {
    const [search, setSearch] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [page, setPage] = useState(0);
    const limit = 50;

    const { data: infraTypes = [] } = useConfigurableTypes('infra');

    const { data, isLoading } = useInfraItems({
        search: search || undefined,
        infra_type: typeFilter || undefined,
        status: statusFilter || undefined,
        limit,
        offset: page * limit,
    });
    const items = data?.items || [];
    const totalItems = data?.total || 0;
    const totalPages = Math.ceil(totalItems / limit);

    const createItem = useCreateInfraItem();
    const deleteItem = useDeleteInfraItem();

    const canCreate = useGlobalPermission('infra_create');
    const canDelete = useGlobalPermission('infra_delete');
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [createOpen, setCreateOpen] = useState(false);
    const [detailItem, setDetailItem] = useState<string | null>(null);
    const [form, setForm] = useState(emptyForm);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createItem.mutateAsync({
                ...form,
                ip_address: form.ip_address || undefined,
                internal_ip: form.internal_ip || undefined,
                hostname: form.hostname || undefined,
                provider: form.provider || undefined,
                region: form.region || undefined,
                os: form.os || undefined,
                point_of_presence: form.point_of_presence || undefined,
                notes: form.notes || undefined,
            });
            toast.success('Infrastructure item created');
            setCreateOpen(false);
            setForm(emptyForm);
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to create'));
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-xl bg-primary/10 border border-primary/20">
                            <Server className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-black text-white tracking-tight">Infrastructure</h1>
                        </div>
                    </div>
                    {canCreate && (
                        <Button onClick={() => setCreateOpen(true)} className="bg-primary hover:bg-primary/90 text-white gap-2">
                            <Plus className="h-4 w-4" />
                            Add Infrastructure
                        </Button>
                    )}
                </div>

                {/* Filters */}
                <div className="flex items-center gap-3 flex-wrap">
                    <div className="relative flex-1 max-w-sm">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                        <Input
                            value={search}
                            onChange={e => { setSearch(e.target.value); setPage(0); }}
                            placeholder="Search name, IP, hostname..."
                            className="pl-9 bg-slate-900/50 border-slate-800 text-white"
                        />
                    </div>
                    <Select value={typeFilter} onValueChange={v => { setTypeFilter(v === 'ALL' ? '' : v); setPage(0); }}>
                        <SelectTrigger className="w-40 bg-slate-900/50 border-slate-800 text-white">
                            <SelectValue placeholder="All Types" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="ALL">All Types</SelectItem>
                            {infraTypes.map(t => (
                                <SelectItem key={t.name} value={t.name}>{t.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <Select value={statusFilter} onValueChange={v => { setStatusFilter(v === 'ALL' ? '' : v); setPage(0); }}>
                        <SelectTrigger className="w-44 bg-slate-900/50 border-slate-800 text-white">
                            <SelectValue placeholder="All Statuses" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="ALL">All Statuses</SelectItem>
                            {STATUS_OPTIONS.map(s => (
                                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <div className="text-xs text-slate-500 ml-auto">
                        {totalItems} item{totalItems !== 1 ? 's' : ''}
                    </div>
                </div>

                {/* Items Grid */}
                {isLoading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                ) : items.length === 0 ? (
                    <Card className="border-slate-800 bg-slate-900/30">
                        <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                            <Server className="h-12 w-12 text-slate-700 mb-3" />
                            <p className="text-slate-400 font-medium">No infrastructure items yet</p>
                            <p className="text-sm text-slate-600 mt-1">Add your red team assets and C2 infrastructure to track them.</p>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="grid gap-3">
                        {items.map(item => (
                            <InfraCard
                                key={item.id}
                                item={item}
                                onView={() => setDetailItem(item.id)}
                                onDelete={async () => {
                                    const ok = await confirm({
                                        title: 'Delete Infrastructure Item',
                                        description: `Are you sure you want to delete "${item.name}"? This will also remove all linked entities.`,
                                        confirmLabel: 'Delete',
                                        variant: 'destructive',
                                    });
                                    if (!ok) return;
                                    await deleteItem.mutateAsync(item.id);
                                    toast.success('Deleted');
                                }}
                                canDelete={canDelete}
                            />
                        ))}
                    </div>
                )}

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2">
                        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)} className="border-slate-800 text-slate-400">
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <span className="text-xs text-slate-500">Page {page + 1} of {totalPages}</span>
                        <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} className="border-slate-800 text-slate-400">
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                )}
            </div>

            {/* ── Create Dialog ─────────────────────────────────── */}
            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-lg max-h-[85vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Server className="h-5 w-5 text-primary" />
                            Add Infrastructure
                        </DialogTitle>
                        <DialogDescription>Register a new red team asset</DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleCreate} className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Name *</Label>
                            <Input
                                value={form.name}
                                onChange={e => setForm({ ...form, name: e.target.value })}
                                required
                                className="bg-slate-800/50 border-slate-700 text-white"
                                placeholder="e.g. East Coast C2, AWS Redirector 1"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Type</Label>
                                <Select value={form.infra_type} onValueChange={v => setForm({ ...form, infra_type: v })}>
                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {infraTypes.map(t => (
                                            <SelectItem key={t.name} value={t.name}>{t.name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Status</Label>
                                <Select value={form.status} onValueChange={v => setForm({ ...form, status: v })}>
                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {STATUS_OPTIONS.map(s => (
                                            <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">IP Address</Label>
                                <Input
                                    value={form.ip_address}
                                    onChange={e => setForm({ ...form, ip_address: e.target.value })}
                                    className="bg-slate-800/50 border-slate-700 text-white font-mono"
                                    placeholder="10.0.0.1"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Internal IP</Label>
                                <Input
                                    value={form.internal_ip}
                                    onChange={e => setForm({ ...form, internal_ip: e.target.value })}
                                    className="bg-slate-800/50 border-slate-700 text-white font-mono"
                                    placeholder="192.168.1.100"
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Hostname</Label>
                            <Input
                                value={form.hostname}
                                onChange={e => setForm({ ...form, hostname: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white font-mono"
                                placeholder="c2.example.com"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Provider</Label>
                                <Input
                                    value={form.provider}
                                    onChange={e => setForm({ ...form, provider: e.target.value })}
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                    placeholder="AWS, Azure, DO..."
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Region</Label>
                                <Input
                                    value={form.region}
                                    onChange={e => setForm({ ...form, region: e.target.value })}
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                    placeholder="us-east-1"
                                />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">OS</Label>
                                <Input
                                    value={form.os}
                                    onChange={e => setForm({ ...form, os: e.target.value })}
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                    placeholder="Ubuntu 22.04"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-300 text-sm">Point of Presence</Label>
                                <Input
                                    value={form.point_of_presence}
                                    onChange={e => setForm({ ...form, point_of_presence: e.target.value })}
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                    placeholder="NYC, London datacenter..."
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-sm">Notes</Label>
                            <Textarea
                                value={form.notes}
                                onChange={e => setForm({ ...form, notes: e.target.value })}
                                className="bg-slate-800/50 border-slate-700 text-white min-h-[80px]"
                                placeholder="Additional details, purpose, configuration..."
                            />
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} className="border-slate-700 text-slate-300 hover:bg-slate-800">Cancel</Button>
                            <Button type="submit" disabled={createItem.isPending} className="bg-primary hover:bg-primary/90 text-white">
                                {createItem.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Creating...</> : 'Create'}
                            </Button>
                        </div>
                    </form>
                </DialogContent>
            </Dialog>

            {/* Detail Dialog */}
            {detailItem && (
                <InfraDetailDialog itemId={detailItem} onClose={() => setDetailItem(null)} />
            )}

            <ConfirmDialog />
        </DashboardLayout>
    );
}
