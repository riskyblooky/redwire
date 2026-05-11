/**
 * assets/page.tsx — Assets List Page
 *
 * Sortable, searchable table of all assets across engagements.
 * Columns: name, type (colour-coded badge), identifier (monospaced),
 * unresolved discussions, and truncated description. Supports:
 *  - Column-header sort (name, type, identifier) persisted to localStorage
 *  - Relevance-ranked search across name, identifier, and description
 *  - Per-row permission-gated view/edit/delete actions
 *  - Real-time WebSocket updates for asset CRUD events
 */
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Plus, Search, Eye, Edit, Trash2, Server, Loader2, MessageSquare,
    ArrowUpDown, ArrowUp, ArrowDown
} from 'lucide-react';
import { useAssets, useDeleteAsset } from '@/lib/hooks/use-assets';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useCanEdit, useCanDelete } from '@/lib/hooks/use-permissions';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { relevanceComparator } from '@/lib/search-relevance';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';

const assetTypeColors: Record<string, string> = {
    IP_ADDRESS: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    DOMAIN: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    URL: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    APPLICATION: 'bg-green-500/10 text-green-400 border-green-500/20',
    SERVER: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    NETWORK: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

const assetTypeLabels: Record<string, string> = {
    IP_ADDRESS: 'IP Address',
    DOMAIN: 'Domain',
    URL: 'URL',
    APPLICATION: 'Application',
    SERVER: 'Server',
    NETWORK: 'Network',
    OTHER: 'Other',
};

type SortField = 'name' | 'asset_type' | 'identifier';
type SortOrder = 'asc' | 'desc';

// Extracted into its own component so hooks are called at the top level
function AssetListRow({ asset, handleView, handleEdit, handleDelete, deleteAsset }: {
    asset: any;
    handleView: (id: string) => void;
    handleEdit: (id: string) => void;
    handleDelete: (id: string) => void;
    deleteAsset: any;
}) {
    const canEdit = useCanEdit(asset.engagement_id, 'asset', asset.created_by);
    const canDelete = useCanDelete(asset.engagement_id, 'asset', asset.created_by);

    return (
        <TableRow key={asset.id} className="border-slate-800 hover:bg-slate-800/50">
            <TableCell className="font-medium text-white">
                {asset.name}
            </TableCell>
            <TableCell>
                <Badge className={assetTypeColors[asset.asset_type] || assetTypeColors.OTHER}>
                    {assetTypeLabels[asset.asset_type] || asset.asset_type}
                </Badge>
            </TableCell>
            <TableCell className="text-slate-300 font-mono text-sm">
                {asset.identifier}
            </TableCell>
            <TableCell>
                {asset.unresolved_thread_count && asset.unresolved_thread_count > 0 ? (
                    <div className="flex items-center gap-2 text-amber-400">
                        <MessageSquare className="h-4 w-4" />
                        <span className="text-sm font-medium">{asset.unresolved_thread_count}</span>
                    </div>
                ) : (
                    <span className="text-slate-600 text-sm">—</span>
                )}
            </TableCell>
            <TableCell className="text-slate-400 text-sm truncate max-w-xs">
                {asset.description || '—'}
            </TableCell>
            <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleView(asset.id)}
                        className="text-slate-400 hover:text-white hover:bg-slate-800"
                    >
                        <Eye className="h-4 w-4" />
                    </Button>
                    {canEdit && (
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleEdit(asset.id)}
                            className="text-slate-400 hover:text-white hover:bg-slate-800"
                        >
                            <Edit className="h-4 w-4" />
                        </Button>
                    )}
                    {canDelete && (
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDelete(asset.id)}
                            disabled={deleteAsset.isPending}
                            className="text-slate-400 hover:text-red-400 hover:bg-slate-800"
                        >
                            {deleteAsset.isPending ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Trash2 className="h-4 w-4" />
                            )}
                        </Button>
                    )}
                </div>
            </TableCell>
        </TableRow>
    );
}

export default function AssetsPage() {
    const router = useRouter();
    const [searchTerm, setSearchTerm] = useState('');
    const [sortField, setSortField] = useState<SortField>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('redwire_sort_assets_field');
            if (saved) return saved as SortField;
        }
        return 'name';
    });
    const [sortOrder, setSortOrder] = useState<SortOrder>(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('redwire_sort_assets_order');
            if (saved) return saved as SortOrder;
        }
        return 'asc';
    });

    // Save preferences to localStorage when they change
    useEffect(() => {
        localStorage.setItem('redwire_sort_assets_field', sortField);
        localStorage.setItem('redwire_sort_assets_order', sortOrder);
    }, [sortField, sortOrder]);

    const { data: assets = [], isLoading, error, refetch } = useAssets();
    const deleteAsset = useDeleteAsset();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const queryClient = useQueryClient();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'asset') {
                    queryClient.invalidateQueries({ queryKey: ['assets'] });
                }
            }
        },
    });

    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortOrder('asc');
        }
    };

    const sortedAssets = [...assets]
        .filter((asset) => {
            const matchesSearch = asset.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                asset.identifier.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (asset.description?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false);
            return matchesSearch;
        })
        .sort(relevanceComparator(
            searchTerm,
            [item => item.name, item => item.identifier],
            (a, b) => {
                const comparison = String(a[sortField]).localeCompare(String(b[sortField]));
                return sortOrder === 'asc' ? comparison : -comparison;
            }
        ));

    const handleView = (id: string) => {
        router.push(`/assets/${id}`);
    };

    const handleEdit = (id: string) => {
        router.push(`/assets/${id}/edit`);
    };

    const handleDelete = async (id: string) => {
        const confirmed = await confirm({
            title: 'Delete Asset',
            description: 'Are you sure you want to delete this asset?',
        });
        if (!confirmed) return;

        try {
            await deleteAsset.mutateAsync(id);
            toast.success('Asset deleted successfully!');
            refetch();
        } catch (error: any) {
            console.error('Failed to delete asset:', error);
            toast.error(getErrorMessage(error, 'Failed to delete asset'));
        }
    };

    const handleCreate = () => {
        router.push('/assets/new');
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
        return sortOrder === 'asc' ? <ArrowUp className="h-3 w-3 ml-1" /> : <ArrowDown className="h-3 w-3 ml-1" />;
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                            <Server className="h-8 w-8 text-primary" />
                            Assets
                        </h1>
                        <p className="text-slate-400 mt-1">Manage target systems and infrastructure</p>
                    </div>
                    <Button onClick={handleCreate} className="bg-primary hover:bg-primary/90 text-white">
                        <Plus className="h-4 w-4 mr-2" />
                        New Asset
                    </Button>
                </div>

                {/* Search */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardContent className="pt-6">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                            <Input
                                placeholder="Search assets..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-10 bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>
                    </CardContent>
                </Card>

                {/* Assets Table */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs shadow-xl">
                    <CardHeader>
                        <CardTitle className="text-white">
                            All Assets {!isLoading && `(${sortedAssets.length})`}
                        </CardTitle>
                        <CardDescription>View and manage your target assets</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <div className="flex items-center justify-center py-10">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : error ? (
                            <div className="text-center py-10 text-red-400">
                                Failed to load assets. Please try again.
                            </div>
                        ) : (
                            <div className="rounded-md border border-slate-800">
                                <Table>
                                    <TableHeader>
                                        <TableRow className="border-slate-800 hover:bg-slate-800/50">
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('name')}
                                            >
                                                <div className="flex items-center">
                                                    Name <SortIcon field="name" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('asset_type')}
                                            >
                                                <div className="flex items-center">
                                                    Type <SortIcon field="asset_type" />
                                                </div>
                                            </TableHead>
                                            <TableHead
                                                className="text-slate-300 cursor-pointer hover:text-white transition-colors"
                                                onClick={() => handleSort('identifier')}
                                            >
                                                <div className="flex items-center">
                                                    Identifier <SortIcon field="identifier" />
                                                </div>
                                            </TableHead>
                                            <TableHead className="text-slate-300">Discussions</TableHead>
                                            <TableHead className="text-slate-300">Description</TableHead>
                                            <TableHead className="text-slate-300 text-right">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {sortedAssets.length === 0 ? (
                                            <TableRow>
                                                <TableCell colSpan={6} className="text-center text-slate-400 py-10">
                                                    No assets found. Create your first asset to get started.
                                                </TableCell>
                                            </TableRow>
                                        ) : (
                                            sortedAssets.map((asset) => (
                                                <AssetListRow
                                                    key={asset.id}
                                                    asset={asset}
                                                    handleView={handleView}
                                                    handleEdit={handleEdit}
                                                    handleDelete={handleDelete}
                                                    deleteAsset={deleteAsset}
                                                />
                                            ))
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
            <ConfirmDialog />
        </DashboardLayout>
    );
}
