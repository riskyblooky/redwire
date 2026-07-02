/**
 * clients/page.tsx — Client Registry Page
 *
 * Hierarchical tree view of all organisations (clients) with drag-and-drop
 * reordering and parent/child nesting. Features:
 *  - Stats strip: total clients, client types, linked engagements.
 *  - Searchable tree with expand-all / collapse-all controls.
 *  - `TreeNode` component renders each client row with a drag handle,
 *    expand/collapse toggle, type badge (colour from configurable types),
 *    engagement count, and context-menu (view, edit, delete).
 *  - Drag-and-drop supports above/below (reorder) and inside (re-parent).
 *  - Create/Edit dialog: name, type selector, parent selector, description,
 *    contact name/email, and internal notes.
 *  - Delete confirmation warns when the client has linked engagements.
 *  - `ClientDetailModal` opens a read-only detail view on click.
 */
'use client';

import { useState, useMemo, useCallback } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
    Building2,
    Plus,
    Search,
    ChevronRight,
    ChevronDown,
    MoreHorizontal,
    Pencil,
    Trash2,
    GripVertical,
    Users,
    Briefcase,
    Loader2,
    FolderTree,
    Mail,
    UserCircle,
    StickyNote,
    Eye,
} from 'lucide-react';
import { toast } from 'sonner';
import { Client, ClientType } from '@/lib/types';
import {
    useClientTree,
    useClients,
    useClientTypes,
    useCreateClient,
    useUpdateClient,
    useDeleteClient,
    useReorderClients,
} from '@/lib/hooks/use-clients';
import { Textarea } from '@/components/ui/textarea';
import { ClientDetailModal } from '@/components/clients/client-detail-modal';
import { ClientStatsPanel } from '@/components/clients/client-stats-panel';
import { apiErrorMessage } from '@/lib/api';

// ============ Client Tree Node Component ============

interface TreeNodeProps {
    node: Client;
    depth: number;
    expandedNodes: Set<string>;
    toggleNode: (id: string) => void;
    onEdit: (client: Client) => void;
    onDelete: (client: Client) => void;
    onView: (client: Client) => void;
    onSelect: (client: Client) => void;
    selectedId: string | null;
    clientTypes: ClientType[];
    onDragStart: (e: React.DragEvent, node: Client) => void;
    onDragOver: (e: React.DragEvent, node: Client) => void;
    onDragLeave: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent, node: Client) => void;
    dragOverId: string | null;
    dragPosition: 'above' | 'below' | 'inside' | null;
}

function TreeNode({ node, depth, expandedNodes, toggleNode, onEdit, onDelete, onView, onSelect, selectedId, clientTypes, onDragStart, onDragOver, onDragLeave, onDrop, dragOverId, dragPosition }: TreeNodeProps) {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children && node.children.length > 0;
    const clientType = clientTypes.find(t => t.id === node.client_type_id);
    const isDragTarget = dragOverId === node.id;
    const isSelected = selectedId === node.id;

    return (
        <div>
            <div
                draggable
                onDragStart={(e) => onDragStart(e, node)}
                onDragOver={(e) => onDragOver(e, node)}
                onDragLeave={onDragLeave}
                onDrop={(e) => onDrop(e, node)}
                className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg transition-all cursor-pointer
                    ${isDragTarget && dragPosition === 'above' ? 'border-t-2 border-t-primary' : ''}
                    ${isDragTarget && dragPosition === 'below' ? 'border-b-2 border-b-primary' : ''}
                    ${isDragTarget && dragPosition === 'inside' ? 'bg-primary/10 border border-primary/30' : ''}
                    ${!isDragTarget && isSelected ? 'bg-primary/10 ring-1 ring-primary/40' : ''}
                    ${!isDragTarget && !isSelected ? 'hover:bg-slate-800/50' : ''}
                `}
                style={{ paddingLeft: `${12 + depth * 24}px` }}
            >
                {/* Drag Handle */}
                <GripVertical className="h-3.5 w-3.5 text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 cursor-grab active:cursor-grabbing" />

                {/* Expand/Collapse Toggle */}
                <button
                    onClick={() => hasChildren && toggleNode(node.id)}
                    className={`shrink-0 w-5 h-5 flex items-center justify-center rounded transition-colors ${hasChildren ? 'hover:bg-slate-700 text-slate-400' : 'text-transparent'
                        }`}
                >
                    {hasChildren ? (
                        isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />
                    ) : (
                        <div className="h-1.5 w-1.5 rounded-full bg-slate-600" />
                    )}
                </button>

                {/* Client Info - clickable to select for stats panel */}
                <div
                    className="flex items-center gap-3 flex-1 min-w-0"
                    onClick={() => onSelect(node)}
                >
                    <Building2 className="h-4 w-4 text-slate-400 shrink-0" />
                    <span className="text-sm font-medium text-white truncate hover:text-primary transition-colors">{node.name}</span>
                    {clientType && (
                        <Badge
                            variant="outline"
                            className="text-[10px] py-0 px-1.5 border-opacity-30 shrink-0"
                            style={{
                                borderColor: clientType.color,
                                color: clientType.color,
                                backgroundColor: `${clientType.color}10`,
                            }}
                        >
                            {clientType.name}
                        </Badge>
                    )}
                    {node.engagement_count > 0 && (
                        <span className="flex items-center gap-1 text-[10px] text-slate-500 shrink-0">
                            <Briefcase className="h-3 w-3" />
                            {node.engagement_count}
                        </span>
                    )}
                </div>

                {/* Contact Info (on hover) */}
                {node.contact_name && (
                    <span className="text-xs text-slate-500 hidden group-hover:inline truncate max-w-[150px]">
                        {node.contact_name}
                    </span>
                )}

                {/* Actions */}
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-white"
                        >
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                        <DropdownMenuItem onClick={() => onView(node)}>
                            <Eye className="h-4 w-4 mr-2" />
                            View Details
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onEdit(node)}>
                            <Pencil className="h-4 w-4 mr-2" />
                            Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            onClick={() => onDelete(node)}
                            className="text-red-400 focus:text-red-400"
                        >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Delete
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>

            {/* Children */}
            {hasChildren && isExpanded && (
                <div className="relative">
                    <div
                        className="absolute top-0 bottom-0 border-l border-slate-800"
                        style={{ left: `${24 + depth * 24}px` }}
                    />
                    {node.children!.map(child => (
                        <TreeNode
                            key={child.id}
                            node={child}
                            depth={depth + 1}
                            expandedNodes={expandedNodes}
                            toggleNode={toggleNode}
                            onEdit={onEdit}
                            onDelete={onDelete}
                            onView={onView}
                            onSelect={onSelect}
                            selectedId={selectedId}
                            clientTypes={clientTypes}
                            onDragStart={onDragStart}
                            onDragOver={onDragOver}
                            onDragLeave={onDragLeave}
                            onDrop={onDrop}
                            dragOverId={dragOverId}
                            dragPosition={dragPosition}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ============ Main Page ============

export default function ClientsPage() {
    const { data: tree, isLoading: treeLoading } = useClientTree();
    const { data: flatClients } = useClients();
    const { data: clientTypes = [] } = useClientTypes();
    const createClient = useCreateClient();
    const updateClient = useUpdateClient();
    const deleteClient = useDeleteClient();

    const reorderClients = useReorderClients();

    // UI State
    const [searchQuery, setSearchQuery] = useState('');
    const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
    const [editingClient, setEditingClient] = useState<Client | null>(null);
    const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<Client | null>(null);
    const [viewTarget, setViewTarget] = useState<Client | null>(null);
    const [selectedClient, setSelectedClient] = useState<Client | null>(null);

    // Drag-and-drop state
    const [draggedNode, setDraggedNode] = useState<Client | null>(null);
    const [dragOverId, setDragOverId] = useState<string | null>(null);
    const [dragPosition, setDragPosition] = useState<'above' | 'below' | 'inside' | null>(null);

    // Form State
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        client_type_id: '',
        parent_id: '',
        contact_name: '',
        contact_email: '',
        notes: '',
    });



    // Toggle expand/collapse
    const toggleNode = (id: string) => {
        setExpandedNodes(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    // Expand all
    const expandAll = () => {
        const allIds = new Set<string>();
        const collect = (nodes: Client[]) => {
            nodes.forEach(n => {
                if (n.children && n.children.length > 0) {
                    allIds.add(n.id);
                    collect(n.children);
                }
            });
        };
        if (tree) collect(tree);
        setExpandedNodes(allIds);
    };

    // Collapse all
    const collapseAll = () => setExpandedNodes(new Set());

    // Helper: get siblings for a given node in the tree
    const getSiblings = useCallback((parentId: string | null | undefined, treeData: Client[]): Client[] => {
        if (!parentId) return treeData;
        const findParent = (nodes: Client[]): Client | undefined => {
            for (const n of nodes) {
                if (n.id === parentId) return n;
                if (n.children) {
                    const found = findParent(n.children);
                    if (found) return found;
                }
            }
            return undefined;
        };
        const parent = findParent(treeData);
        return parent?.children || [];
    }, []);

    // Drag-and-drop handlers
    const handleDragStart = useCallback((e: React.DragEvent, node: Client) => {
        setDraggedNode(node);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', node.id);
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent, targetNode: Client) => {
        e.preventDefault();
        e.stopPropagation();
        if (!draggedNode || draggedNode.id === targetNode.id) return;

        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
        const y = e.clientY - rect.top;
        const height = rect.height;

        if (y < height * 0.25) {
            setDragPosition('above');
        } else if (y > height * 0.75) {
            setDragPosition('below');
        } else {
            setDragPosition('inside');
        }
        setDragOverId(targetNode.id);
    }, [draggedNode]);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragOverId(null);
        setDragPosition(null);
    }, []);

    const handleDrop = useCallback(async (e: React.DragEvent, targetNode: Client) => {
        e.preventDefault();
        e.stopPropagation();

        if (!draggedNode || draggedNode.id === targetNode.id || !tree) {
            setDraggedNode(null);
            setDragOverId(null);
            setDragPosition(null);
            return;
        }

        try {
            const items: { id: string; sort_order: number; parent_id?: string | null }[] = [];

            if (dragPosition === 'inside') {
                // Make dragged node a child of target
                const targetChildren = targetNode.children || [];
                items.push({
                    id: draggedNode.id,
                    sort_order: targetChildren.length,
                    parent_id: targetNode.id,
                });
            } else {
                // Place above or below within the same parent
                const newParentId = targetNode.parent_id || null;
                const siblings = getSiblings(newParentId, tree).filter(s => s.id !== draggedNode.id);
                const targetIdx = siblings.findIndex(s => s.id === targetNode.id);
                const insertIdx = dragPosition === 'above' ? targetIdx : targetIdx + 1;

                const reorderedSiblings = [...siblings];
                reorderedSiblings.splice(insertIdx, 0, draggedNode);

                reorderedSiblings.forEach((sibling, idx) => {
                    items.push({
                        id: sibling.id,
                        sort_order: idx,
                        parent_id: newParentId,
                    });
                });
            }

            await reorderClients.mutateAsync(items);
            toast.success('Client order updated');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to reorder'));
        }

        setDraggedNode(null);
        setDragOverId(null);
        setDragPosition(null);
    }, [draggedNode, dragPosition, tree, getSiblings, reorderClients]);

    // Open create dialog
    const openCreateDialog = (parentId?: string) => {
        setFormData({
            name: '',
            description: '',
            client_type_id: clientTypes.find(t => t.name === 'Organization')?.id || '',
            parent_id: parentId || '',
            contact_name: '',
            contact_email: '',
            notes: '',
        });
        setEditingClient(null);
        setIsCreateDialogOpen(true);
    };

    // Open edit dialog
    const openEditDialog = (client: Client) => {
        setFormData({
            name: client.name,
            description: client.description || '',
            client_type_id: client.client_type_id || '',
            parent_id: client.parent_id || '',
            contact_name: client.contact_name || '',
            contact_email: client.contact_email || '',
            notes: client.notes || '',
        });
        setEditingClient(client);
        setIsCreateDialogOpen(true);
    };

    // Save client
    const handleSaveClient = async () => {
        try {
            const payload = {
                name: formData.name,
                description: formData.description || undefined,
                client_type_id: formData.client_type_id || undefined,
                parent_id: formData.parent_id || undefined,
                contact_name: formData.contact_name || undefined,
                contact_email: formData.contact_email || undefined,
                notes: formData.notes || undefined,
            };

            if (editingClient) {
                await updateClient.mutateAsync({ id: editingClient.id, ...payload });
                toast.success('Client updated successfully');
            } else {
                await createClient.mutateAsync(payload);
                toast.success('Client created successfully');
            }
            setIsCreateDialogOpen(false);
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to save client'));
        }
    };

    // Delete client
    const handleDeleteClient = async () => {
        if (!deleteTarget) return;
        try {
            await deleteClient.mutateAsync(deleteTarget.id);
            toast.success('Client deleted');
            if (selectedClient?.id === deleteTarget.id) setSelectedClient(null);
            setDeleteTarget(null);
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to delete client'));
        }
    };



    // Stats
    const totalClients = flatClients?.length || 0;
    const totalEngagements = flatClients?.reduce((sum, c) => sum + (c.engagement_count || 0), 0) || 0;

    // Filter tree nodes by search
    const filteredTree = useMemo(() => {
        if (!tree || !searchQuery.trim()) return tree || [];
        const q = searchQuery.toLowerCase();

        function filterNodes(nodes: Client[]): Client[] {
            return nodes
                .map(node => {
                    const filteredChildren = node.children ? filterNodes(node.children) : [];
                    const matches = node.name.toLowerCase().includes(q) ||
                        node.contact_name?.toLowerCase().includes(q) ||
                        node.contact_email?.toLowerCase().includes(q);
                    if (matches || filteredChildren.length > 0) {
                        return { ...node, children: filteredChildren };
                    }
                    return null;
                })
                .filter(Boolean) as Client[];
        }

        return filterNodes(tree);
    }, [tree, searchQuery]);

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-6xl">
                {/* Header */}
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                            <Building2 className="h-8 w-8 text-primary" />
                            Client Registry
                        </h1>
                        <p className="text-slate-400 mt-1">Manage your client hierarchy and organization structure</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            onClick={() => openCreateDialog()}
                            className="bg-primary hover:bg-primary/90 text-white"
                        >
                            <Plus className="h-4 w-4 mr-2" />
                            New Client
                        </Button>
                    </div>
                </div>

                {/* Stats Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-primary/10">
                                    <Building2 className="h-5 w-5 text-primary" />
                                </div>
                                <div>
                                    <p className="text-2xl font-bold text-white">{totalClients}</p>
                                    <p className="text-xs text-slate-400">Total Clients</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-cyan-500/10">
                                    <FolderTree className="h-5 w-5 text-cyan-400" />
                                </div>
                                <div>
                                    <p className="text-2xl font-bold text-white">{clientTypes.length}</p>
                                    <p className="text-xs text-slate-400">Client Types</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-amber-500/10">
                                    <Briefcase className="h-5 w-5 text-amber-400" />
                                </div>
                                <div>
                                    <p className="text-2xl font-bold text-white">{totalEngagements}</p>
                                    <p className="text-xs text-slate-400">Linked Engagements</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Tree View */}
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
                        <CardTitle className="text-white text-lg flex items-center gap-2">
                            <FolderTree className="h-5 w-5 text-primary" />
                            Client Hierarchy
                        </CardTitle>
                        <div className="flex items-center gap-2">
                            <Button variant="ghost" size="sm" onClick={expandAll} className="text-xs text-slate-400 hover:text-white">
                                Expand All
                            </Button>
                            <Button variant="ghost" size="sm" onClick={collapseAll} className="text-xs text-slate-400 hover:text-white">
                                Collapse All
                            </Button>
                        </div>
                    </CardHeader>
                    <div className="px-6 pb-4">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search clients..."
                                value={searchQuery}
                                onChange={e => setSearchQuery(e.target.value)}
                                className="pl-9 bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>
                    </div>
                    <CardContent className="pt-0">
                        {treeLoading ? (
                            <div className="flex items-center justify-center py-12">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : filteredTree.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                                <Building2 className="h-12 w-12 mb-3 opacity-20" />
                                <p className="text-sm">
                                    {searchQuery ? 'No clients match your search.' : 'No clients yet. Create your first client to get started.'}
                                </p>
                                {!searchQuery && (
                                    <Button
                                        onClick={() => openCreateDialog()}
                                        variant="outline"
                                        size="sm"
                                        className="mt-4 border-slate-700 text-slate-300"
                                    >
                                        <Plus className="h-4 w-4 mr-2" />
                                        Create Client
                                    </Button>
                                )}
                            </div>
                        ) : (
                            <div className="space-y-0.5">
                                {filteredTree.map(node => (
                                    <TreeNode
                                        key={node.id}
                                        node={node}
                                        depth={0}
                                        expandedNodes={expandedNodes}
                                        toggleNode={toggleNode}
                                        onEdit={openEditDialog}
                                        onDelete={setDeleteTarget}
                                        onView={setViewTarget}
                                        onSelect={setSelectedClient}
                                        selectedId={selectedClient?.id ?? null}
                                        clientTypes={clientTypes}
                                        onDragStart={handleDragStart}
                                        onDragOver={handleDragOver}
                                        onDragLeave={handleDragLeave}
                                        onDrop={handleDrop}
                                        dragOverId={dragOverId}
                                        dragPosition={dragPosition}
                                    />
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Selected client stats / engagements / trends */}
                <ClientStatsPanel
                    client={selectedClient}
                    hasDescendants={!!selectedClient && (flatClients?.some(c => c.parent_id === selectedClient.id) ?? false)}
                />
            </div>

            {/* ============ Create/Edit Client Dialog ============ */}
            <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
                <DialogContent className="sm:max-w-lg bg-slate-900 border-slate-800">
                    <DialogHeader>
                        <DialogTitle className="text-white">
                            {editingClient ? 'Edit Client' : 'Create New Client'}
                        </DialogTitle>
                        <DialogDescription>
                            {editingClient ? 'Update the client information.' : 'Define a new client in your registry.'}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label className="text-slate-200">Name *</Label>
                            <Input
                                value={formData.name}
                                onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                placeholder="e.g., Acme Corporation"
                                className="bg-slate-800/50 border-slate-700 text-white"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label className="text-slate-200">Type</Label>
                                <Select
                                    value={formData.client_type_id}
                                    onValueChange={(v) => setFormData(prev => ({ ...prev, client_type_id: v }))}
                                >
                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue placeholder="Select type" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {clientTypes.map(t => (
                                            <SelectItem key={t.id} value={t.id}>
                                                <span className="flex items-center gap-2">
                                                    <div className="h-2 w-2 rounded-full" style={{ backgroundColor: t.color }} />
                                                    {t.name}
                                                </span>
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-200">Parent</Label>
                                <Select
                                    value={formData.parent_id || "none"}
                                    onValueChange={(v) => setFormData(prev => ({ ...prev, parent_id: v === 'none' ? '' : v }))}
                                >
                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue placeholder="None (top-level)" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="none">None (top-level)</SelectItem>
                                        {(flatClients || [])
                                            .filter(c => c.id !== editingClient?.id)
                                            .map(c => (
                                                <SelectItem key={c.id} value={c.id}>
                                                    {c.name}
                                                </SelectItem>
                                            ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-200">Description</Label>
                            <Textarea
                                value={formData.description}
                                onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
                                placeholder="Brief description of the client..."
                                className="bg-slate-800/50 border-slate-700 text-white min-h-[80px]"
                            />
                        </div>
                        <Separator className="bg-slate-800" />
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label className="text-slate-200 flex items-center gap-1.5">
                                    <UserCircle className="h-3.5 w-3.5" /> Contact Name
                                </Label>
                                <Input
                                    value={formData.contact_name}
                                    onChange={e => setFormData(prev => ({ ...prev, contact_name: e.target.value }))}
                                    placeholder="John Doe"
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-slate-200 flex items-center gap-1.5">
                                    <Mail className="h-3.5 w-3.5" /> Contact Email
                                </Label>
                                <Input
                                    value={formData.contact_email}
                                    onChange={e => setFormData(prev => ({ ...prev, contact_email: e.target.value }))}
                                    placeholder="john@example.com"
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-200 flex items-center gap-1.5">
                                <StickyNote className="h-3.5 w-3.5" /> Notes
                            </Label>
                            <Textarea
                                value={formData.notes}
                                onChange={e => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                                placeholder="Internal notes about this client..."
                                className="bg-slate-800/50 border-slate-700 text-white min-h-[60px]"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setIsCreateDialogOpen(false)}
                            className="border-slate-700 text-slate-300"
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={handleSaveClient}
                            disabled={!formData.name.trim() || createClient.isPending || updateClient.isPending}
                            className="bg-primary hover:bg-primary/90 text-white"
                        >
                            {(createClient.isPending || updateClient.isPending) ? (
                                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</>
                            ) : (
                                editingClient ? 'Save Changes' : 'Create Client'
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* ============ Delete Confirmation ============ */}
            <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
                <AlertDialogContent className="bg-slate-900 border-slate-800">
                    <AlertDialogHeader>
                        <AlertDialogTitle className="text-white">Delete Client</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete <strong className="text-white">{deleteTarget?.name}</strong>?
                            {deleteTarget && deleteTarget.engagement_count > 0 && (
                                <span className="block mt-2 text-amber-400">
                                    ⚠ This client has {deleteTarget.engagement_count} linked engagement(s). You must reassign them first.
                                </span>
                            )}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel className="border-slate-700 text-slate-300">Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDeleteClient}
                            className="bg-red-600 hover:bg-red-700"
                            disabled={deleteClient.isPending}
                        >
                            {deleteClient.isPending ? 'Deleting...' : 'Delete'}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>



            {/* ============ Client Detail View Modal ============ */}
            <ClientDetailModal
                client={viewTarget}
                open={!!viewTarget}
                onOpenChange={(open) => !open && setViewTarget(null)}
                clientTypes={clientTypes}
                allClients={flatClients || []}
            />
        </DashboardLayout>
    );
}
