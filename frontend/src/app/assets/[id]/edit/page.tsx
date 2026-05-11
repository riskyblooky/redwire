/**
 * assets/[id]/edit/page.tsx — Edit Asset Page
 *
 * Pre-populated edit form mirroring the create page layout. The engagement
 * field is locked (cannot be changed after creation). Loads existing asset
 * data and populates name, type (from configurable types), identifier,
 * description, and internal notes. Navigates to the asset detail view
 * on save or back to the engagement's assets tab when cancelled.
 */
'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useParams } from '@/lib/hooks/use-params';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { ArrowLeft, Save, Loader2, Plus, Trash2, Network, Pencil, Check, X } from 'lucide-react';
import { useAsset, useUpdateAsset, useAddAssetPort, useDeleteAssetPort, useUpdateAssetPort } from '@/lib/hooks/use-assets';
import { Badge } from '@/components/ui/badge';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { Asset } from '@/lib/types';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useNavigationGuard } from '@/lib/hooks/use-navigation-guard';


export default function EditAssetPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const returnEngagementId = searchParams.get('engagementId');
    const returnTab = searchParams.get('tab') || 'assets';

    const { data: asset, isLoading: isLoadingAsset } = useAsset(id);
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const updateAsset = useUpdateAsset();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const addPort = useAddAssetPort();
    const deletePort = useDeleteAssetPort();
    const updatePort = useUpdateAssetPort();
    const { data: assetTypes = [] } = useConfigurableTypes('asset');
    const [isDirty, setIsDirty] = useState(false);

    // Port editing state
    const [editingPortId, setEditingPortId] = useState<string | null>(null);
    const [editPortData, setEditPortData] = useState({ port_number: '', protocol: 'TCP' as 'TCP' | 'UDP', service_name: '', state: 'OPEN' as 'OPEN' | 'CLOSED' | 'FILTERED', version: '' });

    const handleStartEdit = (port: any) => {
        setEditingPortId(port.id);
        setEditPortData({
            port_number: String(port.port_number),
            protocol: port.protocol || 'TCP',
            service_name: port.service_name || '',
            state: port.state || 'OPEN',
            version: port.version || '',
        });
    };

    const handleSaveEdit = async (portId: string) => {
        const portNum = parseInt(editPortData.port_number, 10);
        if (!portNum || portNum < 1 || portNum > 65535) {
            toast.error('Port must be between 1 and 65535');
            return;
        }
        try {
            await updatePort.mutateAsync({
                assetId: id,
                portId,
                port_number: portNum,
                protocol: editPortData.protocol,
                service_name: editPortData.service_name || undefined,
                state: editPortData.state,
                version: editPortData.version || undefined,
            });
            setEditingPortId(null);
            toast.success('Port updated');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to update port');
        }
    };

    // Port add form state
    const [newPort, setNewPort] = useState({ port_number: '', protocol: 'TCP' as 'TCP' | 'UDP', service_name: '', state: 'OPEN' as 'OPEN' | 'CLOSED' | 'FILTERED', version: '' });
    const [showPortForm, setShowPortForm] = useState(false);

    const handleAddPort = async () => {
        const portNum = parseInt(newPort.port_number, 10);
        if (!portNum || portNum < 1 || portNum > 65535) {
            toast.error('Port must be between 1 and 65535');
            return;
        }
        try {
            await addPort.mutateAsync({
                assetId: id,
                port_number: portNum,
                protocol: newPort.protocol,
                service_name: newPort.service_name || undefined,
                state: newPort.state,
                version: newPort.version || undefined,
            });
            setNewPort({ port_number: '', protocol: 'TCP', service_name: '', state: 'OPEN', version: '' });
            setShowPortForm(false);
            toast.success(`Port ${portNum}/${newPort.protocol} added`);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to add port');
        }
    };

    const handleDeletePort = async (portId: string, portNumber: number) => {
        try {
            await deletePort.mutateAsync({ assetId: id, portId });
            toast.success(`Port ${portNumber} removed`);
        } catch (error: any) {
            toast.error('Failed to remove port');
        }
    };

    const [formData, setFormData] = useState({
        name: '',
        engagement_id: '',
        asset_type: 'DOMAIN',
        identifier: '',
        description: '',
        notes: '',
    });

    // Normalize a stored asset_type string against the loaded types list
    // (handles old SCREAMING_SNAKE_CASE values like IP_ADDRESS vs current "IP Address")
    const normalizeType = (raw: string, types: { name: string }[]) => {
        if (!raw || !types.length) return raw;
        const normalize = (s: string) => s.toLowerCase().replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
        const match = types.find(t => normalize(t.name) === normalize(raw));
        return match ? match.name : raw;
    };

    // Populate form when asset data loads
    useEffect(() => {
        if (asset) {
            setFormData({
                name: asset.name || '',
                engagement_id: asset.engagement_id || '',
                asset_type: normalizeType((asset.asset_type as string) || '', assetTypes),
                identifier: asset.identifier || '',
                description: asset.description || '',
                notes: asset.notes || '',
            });
            setIsDirty(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [asset?.id]);

    // Re-normalize type when configurable types finish loading (async race)
    useEffect(() => {
        if (asset && assetTypes.length > 0) {
            const normalized = normalizeType((asset.asset_type as string) || '', assetTypes);
            setFormData(prev => {
                if (prev.asset_type === normalized) return prev; // no-op, avoid re-render
                return { ...prev, asset_type: normalized };
            });
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [assetTypes.length]);

    const handleChange = (field: string, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setIsDirty(true);
    };

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        try {
            await updateAsset.mutateAsync({ id: id, ...formData });
            setIsDirty(false);
            router.push(`/assets/${id}`);
        } catch (error: any) {
            console.error('Failed to update asset:', error);
            toast.error(error.response?.data?.detail || 'Failed to update asset');
        }
    };

    const getBackPath = () => returnEngagementId
        ? `/engagements/${returnEngagementId}?tab=${returnTab}`
        : `/assets/${id}`;

    const { navigateWithGuard } = useNavigationGuard(isDirty, confirm);

    if (isLoadingAsset) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (!asset) {
        return (
            <DashboardLayout>
                <div className="p-6">
                    <div className="text-center text-red-400">
                        Asset not found
                    </div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
          <div className="flex flex-col min-h-full">
            {/* ── Sticky header ── */}
            <div className="sticky top-0 z-20 bg-slate-950/90 backdrop-blur-md border-b border-slate-800/50">
                <div className="flex items-center gap-4 px-6 pt-5 pb-4">
                    <Button
                        variant="ghost" size="icon"
                        onClick={() => navigateWithGuard(getBackPath())}
                        className="text-slate-400 hover:text-white hover:bg-slate-800"
                    >
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-2xl font-bold text-white tracking-tight">Edit Asset</h1>
                        <p className="text-slate-400 text-sm mt-0.5 truncate">{asset.name}</p>
                    </div>
                </div>
            </div>
            {/* Content — two-column grid: details left, ports right */}
            <div className="p-6 pb-24 flex-1">
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              {/* Left column: form */}
              <div className="lg:col-span-3">
                <form id="asset-edit-form" onSubmit={handleSubmit}>
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader>
                            <CardTitle className="text-white">Asset Details</CardTitle>
                            <CardDescription>Update asset information. Engagement is locked after creation.</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {/* Engagement Selection */}
                            <div className="space-y-2">
                                <Label htmlFor="engagement_id" className="text-slate-200">
                                    Engagement *
                                </Label>
                                {isLoadingAsset || isLoadingEngagements ? (
                                    <div className="h-10 bg-slate-800/50 border border-slate-700 rounded-md flex items-center px-3">
                                        <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
                                    </div>
                                ) : (
                                    <div className="space-y-1">
                                        <Input
                                            value={engagements.find(e => e.id === formData.engagement_id)?.name || 'Unknown Engagement'}
                                            disabled
                                            className="bg-slate-800/50 border-slate-700 text-slate-400 cursor-not-allowed"
                                        />
                                        <p className="text-[10px] text-slate-500 italic">Engagement cannot be changed after creation.</p>
                                    </div>
                                )}
                            </div>

                            {/* Name */}
                            <div className="space-y-2">
                                <Label htmlFor="name" className="text-slate-200">
                                    Asset Name *
                                </Label>
                                <Input
                                    id="name"
                                    value={formData.name}
                                    onChange={(e) => handleChange('name', e.target.value)}
                                    placeholder="e.g., Corporate Website, External VPN"
                                    required
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                />
                            </div>

                            {/* Type and Identifier */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="space-y-2">
                                    <Label htmlFor="asset_type" className="text-slate-200">
                                        Asset Type *
                                    </Label>
                                    <Select
                                        key={`${asset?.id}-${formData.asset_type}-${assetTypes.length}`}
                                        value={formData.asset_type}
                                        onValueChange={(value) => handleChange('asset_type', value)}
                                    >
                                        <SelectTrigger id="asset_type" className="bg-slate-800/50 border-slate-700 text-white">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {assetTypes.map((type) => (
                                                <SelectItem key={type.id} value={type.name}>
                                                    {type.name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="identifier" className="text-slate-200">
                                        Identifier / URL *
                                    </Label>
                                    <Input
                                        id="identifier"
                                        value={formData.identifier}
                                        onChange={(e) => handleChange('identifier', e.target.value)}
                                        placeholder="e.g., 192.168.1.1, example.com, https://app.acme.com"
                                        required
                                        className="bg-slate-800/50 border-slate-700 text-white font-mono"
                                    />
                                </div>
                            </div>

                            {/* Description */}
                            <div className="space-y-2">
                                <Label htmlFor="description" className="text-slate-200">
                                    Description
                                </Label>
                                <MarkdownEditor
                                    id="description"
                                    value={formData.description}
                                    onChange={(val) => handleChange('description', val)}
                                    placeholder="Brief description of the asset..."
                                    minHeight="100px"
                                />
                            </div>

                            {/* Notes */}
                            <div className="space-y-2">
                                <Label htmlFor="notes" className="text-slate-200">
                                    Internal Notes
                                </Label>
                                <MarkdownEditor
                                    id="notes"
                                    value={formData.notes}
                                    onChange={(val) => handleChange('notes', val)}
                                    placeholder="Any internal notes about this asset..."
                                    minHeight="100px"
                                />
                            </div>

                        </CardContent>
                    </Card>
                </form>
              </div>

              {/* Right column: ports */}
              <div className="lg:col-span-2">
                <div className="lg:sticky lg:top-24">
                {/* ── Ports Section ── */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Network className="h-4 w-4 text-cyan-400" />
                                <CardTitle className="text-white text-base">Ports</CardTitle>
                                {(asset.ports?.length ?? 0) > 0 && (
                                    <Badge variant="secondary" className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20 text-xs">
                                        {(asset.ports ?? []).length}
                                    </Badge>
                                )}
                            </div>
                            <Button
                                size="sm" variant="ghost"
                                onClick={() => setShowPortForm(!showPortForm)}
                                className="text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 gap-1.5 text-xs"
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Add Port
                            </Button>
                        </div>
                        <p className="text-slate-500 text-xs mt-1">Ports are saved immediately — no need to click Save Changes.</p>
                    </CardHeader>
                    <CardContent className="pt-0">
                        {/* Inline add form */}
                        {showPortForm && (
                            <div className="mb-4 p-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5">
                                <div className="grid grid-cols-2 gap-2">
                                    <div>
                                        <Label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Port *</Label>
                                        <Input
                                            type="number" min={1} max={65535}
                                            value={newPort.port_number}
                                            onChange={e => setNewPort(p => ({ ...p, port_number: e.target.value }))}
                                            placeholder="443"
                                            className="bg-slate-800/50 border-slate-700 text-white h-8 text-sm font-mono"
                                        />
                                    </div>
                                    <div>
                                        <Label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Protocol</Label>
                                        <Select value={newPort.protocol} onValueChange={v => setNewPort(p => ({ ...p, protocol: v as 'TCP' | 'UDP' }))}>
                                            <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white h-8 text-sm">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="TCP">TCP</SelectItem>
                                                <SelectItem value="UDP">UDP</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Service</Label>
                                        <Input
                                            value={newPort.service_name}
                                            onChange={e => setNewPort(p => ({ ...p, service_name: e.target.value }))}
                                            placeholder="https"
                                            className="bg-slate-800/50 border-slate-700 text-white h-8 text-sm"
                                        />
                                    </div>
                                    <div>
                                        <Label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">State</Label>
                                        <Select value={newPort.state} onValueChange={v => setNewPort(p => ({ ...p, state: v as any }))}>
                                            <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white h-8 text-sm">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="OPEN">Open</SelectItem>
                                                <SelectItem value="CLOSED">Closed</SelectItem>
                                                <SelectItem value="FILTERED">Filtered</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 block">Version</Label>
                                        <Input
                                            value={newPort.version}
                                            onChange={e => setNewPort(p => ({ ...p, version: e.target.value }))}
                                            placeholder="nginx 1.24"
                                            className="bg-slate-800/50 border-slate-700 text-white h-8 text-sm"
                                        />
                                    </div>
                                </div>
                                <div className="flex justify-end gap-2 mt-3">
                                    <Button size="sm" variant="ghost" onClick={() => setShowPortForm(false)}
                                        className="text-slate-400 hover:text-white h-7 text-xs">
                                        Cancel
                                    </Button>
                                    <Button size="sm" onClick={handleAddPort} disabled={addPort.isPending}
                                        className="bg-cyan-600 hover:bg-cyan-500 text-white h-7 text-xs gap-1">
                                        {addPort.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
                                        Add
                                    </Button>
                                </div>
                            </div>
                        )}

                        {/* Port table */}
                        {(asset.ports?.length ?? 0) > 0 ? (
                            <div className="rounded-md border border-slate-800 overflow-hidden">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-slate-800 bg-slate-800/30">
                                            <th className="text-left text-[10px] uppercase tracking-wider text-slate-500 font-medium px-3 py-2">Port</th>
                                            <th className="text-left text-[10px] uppercase tracking-wider text-slate-500 font-medium px-3 py-2">Proto</th>
                                            <th className="text-left text-[10px] uppercase tracking-wider text-slate-500 font-medium px-3 py-2">Service</th>
                                            <th className="text-left text-[10px] uppercase tracking-wider text-slate-500 font-medium px-3 py-2">State</th>
                                            <th className="text-left text-[10px] uppercase tracking-wider text-slate-500 font-medium px-3 py-2">Version</th>
                                            <th className="w-10"></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(asset.ports ?? [])
                                            .sort((a: any, b: any) => a.port_number - b.port_number)
                                            .map((port: any) => (
                                            <tr key={port.id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                                                {editingPortId === port.id ? (
                                                    /* ── Editing row ── */
                                                    <>
                                                        <td className="px-2 py-1.5">
                                                            <Input type="number" min={1} max={65535}
                                                                value={editPortData.port_number}
                                                                onChange={e => setEditPortData(p => ({ ...p, port_number: e.target.value }))}
                                                                className="bg-slate-800/50 border-slate-700 text-white h-7 text-xs font-mono w-16"
                                                            />
                                                        </td>
                                                        <td className="px-2 py-1.5">
                                                            <Select value={editPortData.protocol} onValueChange={v => setEditPortData(p => ({ ...p, protocol: v as any }))}>
                                                                <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white h-7 text-xs w-[70px]">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    <SelectItem value="TCP">TCP</SelectItem>
                                                                    <SelectItem value="UDP">UDP</SelectItem>
                                                                </SelectContent>
                                                            </Select>
                                                        </td>
                                                        <td className="px-2 py-1.5">
                                                            <Input value={editPortData.service_name}
                                                                onChange={e => setEditPortData(p => ({ ...p, service_name: e.target.value }))}
                                                                placeholder="service"
                                                                className="bg-slate-800/50 border-slate-700 text-white h-7 text-xs"
                                                            />
                                                        </td>
                                                        <td className="px-2 py-1.5">
                                                            <Select value={editPortData.state} onValueChange={v => setEditPortData(p => ({ ...p, state: v as any }))}>
                                                                <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white h-7 text-xs w-[90px]">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    <SelectItem value="OPEN">Open</SelectItem>
                                                                    <SelectItem value="CLOSED">Closed</SelectItem>
                                                                    <SelectItem value="FILTERED">Filtered</SelectItem>
                                                                </SelectContent>
                                                            </Select>
                                                        </td>
                                                        <td className="px-2 py-1.5">
                                                            <Input value={editPortData.version}
                                                                onChange={e => setEditPortData(p => ({ ...p, version: e.target.value }))}
                                                                placeholder="version"
                                                                className="bg-slate-800/50 border-slate-700 text-white h-7 text-xs"
                                                            />
                                                        </td>
                                                        <td className="px-1 py-1.5">
                                                            <div className="flex gap-0.5">
                                                                <Button variant="ghost" size="icon"
                                                                    onClick={() => handleSaveEdit(port.id)}
                                                                    disabled={updatePort.isPending}
                                                                    className="h-6 w-6 text-green-400 hover:text-green-300 hover:bg-green-500/10">
                                                                    {updatePort.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                                                                </Button>
                                                                <Button variant="ghost" size="icon"
                                                                    onClick={() => setEditingPortId(null)}
                                                                    className="h-6 w-6 text-slate-500 hover:text-white hover:bg-slate-700">
                                                                    <X className="h-3.5 w-3.5" />
                                                                </Button>
                                                            </div>
                                                        </td>
                                                    </>
                                                ) : (
                                                    /* ── Display row ── */
                                                    <>
                                                        <td className="px-3 py-2 font-mono text-white font-medium">{port.port_number}</td>
                                                        <td className="px-3 py-2">
                                                            <span className={cn(
                                                                'text-xs font-medium px-1.5 py-0.5 rounded',
                                                                port.protocol === 'TCP' ? 'bg-blue-500/10 text-blue-400' : 'bg-amber-500/10 text-amber-400'
                                                            )}>
                                                                {port.protocol}
                                                            </span>
                                                        </td>
                                                        <td className="px-3 py-2 text-slate-300">{port.service_name || <span className="text-slate-600">—</span>}</td>
                                                        <td className="px-3 py-2">
                                                            <span className={cn(
                                                                'text-xs font-medium px-1.5 py-0.5 rounded',
                                                                port.state === 'OPEN' ? 'bg-green-500/10 text-green-400'
                                                                    : port.state === 'FILTERED' ? 'bg-amber-500/10 text-amber-400'
                                                                    : 'bg-red-500/10 text-red-400'
                                                            )}>
                                                                {port.state}
                                                            </span>
                                                        </td>
                                                        <td className="px-3 py-2 text-slate-400 text-xs">{port.version || <span className="text-slate-600">—</span>}</td>
                                                        <td className="px-1 py-2">
                                                            <div className="flex gap-0.5">
                                                                <Button variant="ghost" size="icon"
                                                                    onClick={() => handleStartEdit(port)}
                                                                    className="h-6 w-6 text-slate-500 hover:text-cyan-400 hover:bg-cyan-500/10">
                                                                    <Pencil className="h-3 w-3" />
                                                                </Button>
                                                                <Button variant="ghost" size="icon"
                                                                    onClick={() => handleDeletePort(port.id, port.port_number)}
                                                                    className="h-6 w-6 text-slate-500 hover:text-red-400 hover:bg-red-500/10">
                                                                    <Trash2 className="h-3.5 w-3.5" />
                                                                </Button>
                                                            </div>
                                                        </td>
                                                    </>
                                                )}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : !showPortForm ? (
                            <div className="text-center py-6 text-sm text-slate-500">
                                <Network className="h-8 w-8 mx-auto mb-2 text-slate-600" />
                                No ports detected. Click "Add Port" above to add one.
                            </div>
                        ) : null}
                    </CardContent>
                </Card>
                </div>
              </div>
              </div>
            </div>

            {/* ── Save bar — only when dirty, pinned to the bottom ── */}
            <div className={cn(
                'sticky bottom-0 z-30 border-t transition-all duration-200',
                isDirty
                    ? 'border-primary/30 bg-slate-950/95 backdrop-blur-md'
                    : 'h-0 overflow-hidden border-transparent opacity-0 pointer-events-none'
            )}>
                <div className="px-6 pr-20 py-3 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-2 text-sm text-amber-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                        <span>Unsaved changes</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost" size="sm"
                            onClick={() => navigateWithGuard(getBackPath())}
                            className="text-slate-400 hover:text-white"
                        >
                            Discard
                        </Button>
                        <Button
                            size="sm"
                            onClick={handleSubmit}
                            disabled={updateAsset.isPending}
                            className="bg-primary hover:bg-primary/90 text-white gap-2"
                        >
                            {updateAsset.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                            Save Changes
                        </Button>
                    </div>
                </div>
            </div>
          </div>
          <ConfirmDialog />
        </DashboardLayout>
    );
}
