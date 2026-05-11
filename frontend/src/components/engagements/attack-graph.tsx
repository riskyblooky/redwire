'use client';

import { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    Handle,
    Position,
    useNodesState,
    useEdgesState,
    MarkerType,
    Panel,
    useReactFlow,
    ReactFlowProvider,
    type Node,
    type Edge,
    type Connection,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import Dagre from '@dagrejs/dagre';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import {
    Monitor, AlertTriangle, ClipboardCheck, Sparkles,
    Loader2, Maximize2, Minimize2, LayoutDashboard, X, Eye, EyeOff, RefreshCw,
    Crosshair, Plus, Trash2, Link, Download, BookMarked, Pencil, Check
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';


// ── Types ──
interface GraphNodeData {
    label: string;
    subtitle?: string;
    severity?: string;
    status?: string;
    assetType?: string;
    inScope?: boolean;
    isPwned?: boolean;
    entityId?: string;
    [key: string]: unknown;
}

interface GraphData {
    nodes: Array<{
        id: string;
        type: string;
        data: GraphNodeData;
    }>;
    edges: Array<{
        id: string;
        source: string;
        target: string;
        label?: string;
    }>;
    pinned_positions?: Record<string, { x: number; y: number }> | null;
    pinned_by?: string | null;
    pinned_at?: string | null;
}

interface SavedLayout {
    id: string;
    name: string;
    is_active: boolean;
    pinned_by: string;
    pinned_by_username: string;
    pinned_at: string;
}

function useGraphLayouts(engagementId: string) {
    return useQuery<SavedLayout[]>({
        queryKey: ['attack-graph-layouts', engagementId],
        queryFn: async () => {
            const res = await api.get(`/engagements/${engagementId}/attack-graph/layouts`);
            return res.data;
        },
        staleTime: 30_000,
    });
}

// ── Dagre Layout ──
function getLayoutedElements(
    nodes: Node[],
    edges: Edge[],
    direction: 'LR' | 'TB' = 'LR'
): { nodes: Node[]; edges: Edge[] } {
    const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 120, marginx: 30, marginy: 30 });

    nodes.forEach((node) => {
        g.setNode(node.id, { width: 240, height: 80 });
    });
    edges.forEach((edge) => {
        g.setEdge(edge.source, edge.target);
    });

    Dagre.layout(g);

    const layoutedNodes = nodes.map((node) => {
        const pos = g.node(node.id);
        return {
            ...node,
            position: { x: pos.x - 120, y: pos.y - 40 },
        };
    });

    return { nodes: layoutedNodes, edges };
}

// ── Colors / Styles ──
const severityColors: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#3b82f6',
    info: '#6b7280',
};

const typeConfig: Record<string, { bg: string; border: string; text: string; icon: React.ElementType; accent: string }> = {
    asset: { bg: '#0e1a2e', border: '#22d3ee', text: '#22d3ee', icon: Monitor, accent: 'bg-cyan-500/20 text-cyan-400' },
    testcase: { bg: '#1a1506', border: '#f59e0b', text: '#f59e0b', icon: ClipboardCheck, accent: 'bg-amber-500/20 text-amber-400' },
    finding: { bg: '#1f0a0a', border: '#ef4444', text: '#ef4444', icon: AlertTriangle, accent: 'bg-red-500/20 text-red-400' },
    cleanup: { bg: '#0d1a06', border: '#84cc16', text: '#84cc16', icon: Sparkles, accent: 'bg-lime-500/20 text-lime-400' },
    attacker: { bg: '#1a0d1f', border: '#a855f7', text: '#a855f7', icon: Crosshair, accent: 'bg-primary/20 text-primary' },
};

// ── Custom Node ──
function GraphNode({ data, type }: { data: GraphNodeData; type?: string }) {
    const config = typeConfig[type || 'asset'] || typeConfig.asset;
    const Icon = config.icon;
    const borderColor = type === 'finding' ? (severityColors[data.severity || 'info'] || config.border) : config.border;

    return (
        <div
            className="rounded-lg shadow-lg px-3 py-2.5 min-w-[200px] max-w-[260px] cursor-pointer transition-shadow hover:shadow-xl relative"
            style={{
                background: config.bg,
                border: `1.5px solid ${borderColor}`,
            }}
        >
            <Handle type="target" position={Position.Left} className="!w-2 !h-2 !border-slate-700 !bg-slate-500" />
            <Handle type="source" position={Position.Right} className="!w-2 !h-2 !border-slate-700 !bg-slate-500" />
            <div className="flex items-center gap-2">
                <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: config.text }} />
                <span className="text-xs font-bold truncate text-white" title={data.label}>
                    {data.label}
                </span>
            </div>
            {data.subtitle && (
                <p className="text-[10px] text-slate-500 mt-0.5 truncate" title={data.subtitle || ''}>
                    {data.subtitle}
                </p>
            )}
            <div className="flex items-center gap-1 mt-1 flex-wrap">
                {type === 'finding' && data.severity && (
                    <span
                        className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded"
                        style={{
                            color: severityColors[data.severity] || '#6b7280',
                            background: `${severityColors[data.severity] || '#6b7280'}22`,
                        }}
                    >
                        {data.severity}
                    </span>
                )}
                {data.status && (
                    <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                        {data.status}
                    </span>
                )}
                {type === 'asset' && data.isPwned && (
                    <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 font-bold">
                        PWNED
                    </span>
                )}
            </div>
        </div>
    );
}

const nodeTypes = {
    asset: (props: any) => <GraphNode data={props.data} type="asset" />,
    testcase: (props: any) => <GraphNode data={props.data} type="testcase" />,
    finding: (props: any) => <GraphNode data={props.data} type="finding" />,
    cleanup: (props: any) => <GraphNode data={props.data} type="cleanup" />,
    attacker: (props: any) => <GraphNode data={props.data} type="attacker" />,
};

// ── Layouts Popover ──
function LayoutsPopover({ engagementId, layouts, onRefreshLayouts, onRefreshGraph, getPositions }: {
    engagementId: string;
    layouts: SavedLayout[];
    onRefreshLayouts: () => void;
    onRefreshGraph: () => void;
    getPositions: () => Record<string, { x: number; y: number }>;
}) {
    const [open, setOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [showSave, setShowSave] = useState(false);
    const [newName, setNewName] = useState('');
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState('');
    const popoverRef = useRef<HTMLDivElement>(null);

    // Close on outside click
    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (popoverRef.current && !popoverRef.current.contains(e.target as Element)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    const handleSave = async () => {
        if (!newName.trim()) { toast.warning('Enter a name for this layout'); return; }
        setSaving(true);
        try {
            const positions = getPositions();
            await api.post(`/engagements/${engagementId}/attack-graph/layouts`, {
                name: newName.trim(),
                positions,
                make_active: true,
            });
            toast.success(`Layout "${newName.trim()}" saved`);
            setNewName('');
            setShowSave(false);
            onRefreshLayouts();
            onRefreshGraph();
        } catch {
            toast.error('Failed to save layout');
        } finally {
            setSaving(false);
        }
    };

    const handleActivate = async (layout: SavedLayout) => {
        try {
            await api.put(`/engagements/${engagementId}/attack-graph/layouts/${layout.id}/activate`);
            toast.success(`"${layout.name}" applied`);
            onRefreshLayouts();
            onRefreshGraph();
        } catch {
            toast.error('Failed to load layout');
        }
    };

    const handleRename = async (layout: SavedLayout) => {
        if (!renameValue.trim()) return;
        try {
            await api.put(`/engagements/${engagementId}/attack-graph/layouts/${layout.id}`, { name: renameValue.trim() });
            toast.success('Renamed');
            setRenamingId(null);
            onRefreshLayouts();
        } catch {
            toast.error('Failed to rename');
        }
    };

    const handleDelete = async (layout: SavedLayout) => {
        try {
            await api.delete(`/engagements/${engagementId}/attack-graph/layouts/${layout.id}`);
            toast.success(`"${layout.name}" deleted`);
            onRefreshLayouts();
            if (layout.is_active) onRefreshGraph();
        } catch {
            toast.error('Failed to delete layout');
        }
    };

    const hiddenCount = 0; // no hidden concept here, just show badge on layout count

    return (
        <div className="relative" ref={popoverRef}>
            <Button
                size="icon"
                variant="outline"
                className={`h-7 w-7 border-slate-700 bg-slate-900/90 backdrop-blur-xl relative ${
                    layouts.some(l => l.is_active)
                        ? 'text-indigo-400 border-indigo-500/50'
                        : 'text-slate-300 hover:bg-slate-800'
                }`}
                onClick={() => setOpen(v => !v)}
                title="Manage saved layouts"
            >
                <BookMarked className="h-3.5 w-3.5" />
                {layouts.length > 0 && (
                    <span className="absolute -top-1 -right-1 h-3.5 w-3.5 rounded-full bg-indigo-500 text-[8px] font-bold text-white flex items-center justify-center">
                        {layouts.length}
                    </span>
                )}
            </Button>

            {open && (
                <div className="absolute right-0 top-9 z-[200] w-72 bg-slate-950 border border-slate-800 rounded-xl shadow-2xl overflow-hidden">
                    {/* Header */}
                    <div className="flex items-center justify-between px-3 py-2.5 border-b border-slate-800">
                        <div className="flex items-center gap-2">
                            <BookMarked className="h-3.5 w-3.5 text-indigo-400" />
                            <span className="text-xs font-bold text-white">Saved Layouts</span>
                        </div>
                        <button onClick={() => setOpen(false)} className="text-slate-500 hover:text-white">
                            <X className="h-3.5 w-3.5" />
                        </button>
                    </div>

                    {/* Layout list */}
                    <div className="max-h-52 overflow-y-auto">
                        {layouts.length === 0 ? (
                            <p className="text-xs text-slate-500 text-center py-5">No saved layouts yet.</p>
                        ) : (
                            layouts.map(layout => (
                                <div
                                    key={layout.id}
                                    className={`group flex items-center gap-2 px-3 py-2 border-b border-slate-800/50 last:border-0 transition-colors ${
                                        !layout.is_active && renamingId !== layout.id
                                            ? 'cursor-pointer hover:bg-primary/90/10'
                                            : 'hover:bg-slate-900'
                                    }`}
                                    onClick={() => {
                                        if (!layout.is_active && renamingId !== layout.id) {
                                            handleActivate(layout);
                                        }
                                    }}
                                    title={!layout.is_active ? 'Click to apply this layout' : undefined}
                                >
                                    {/* Active indicator */}
                                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                                        layout.is_active ? 'bg-indigo-400' : 'bg-slate-700'
                                    }`} />

                                    {/* Name or rename input */}
                                    {renamingId === layout.id ? (
                                        <div className="flex items-center gap-1 flex-1 min-w-0">
                                            <input
                                                autoFocus
                                                className="flex-1 min-w-0 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-xs text-white focus:outline-none focus:border-primary"
                                                value={renameValue}
                                                onChange={e => setRenameValue(e.target.value)}
                                                onKeyDown={e => { if (e.key === 'Enter') handleRename(layout); if (e.key === 'Escape') setRenamingId(null); }}
                                                onClick={e => e.stopPropagation()}
                                            />
                                            <button onClick={(e) => { e.stopPropagation(); handleRename(layout); }} className="text-indigo-400 hover:text-indigo-300">
                                                <Check className="h-3 w-3" />
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="flex-1 min-w-0">
                                            <p className={`text-xs font-medium truncate ${layout.is_active ? 'text-indigo-300' : 'text-white'}`}>{layout.name}</p>
                                            <p className="text-[10px] text-slate-500">
                                                {layout.pinned_by_username} · {new Date(layout.pinned_at).toLocaleDateString()}
                                            </p>
                                        </div>
                                    )}

                                    {/* Actions */}
                                    {renamingId !== layout.id && (
                                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                                            {layout.is_active && (
                                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400">Active</span>
                                            )}
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setRenamingId(layout.id); setRenameValue(layout.name); }}
                                                className="text-slate-500 hover:text-slate-300 transition-colors"
                                                title="Rename"
                                            >
                                                <Pencil className="h-3 w-3" />
                                            </button>
                                            {layout.name !== 'Default' && (
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDelete(layout); }}
                                                    className="text-slate-500 hover:text-red-400 transition-colors"
                                                    title="Delete"
                                                >
                                                    <Trash2 className="h-3 w-3" />
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))
                        )}
                    </div>

                    {/* Save current */}
                    <div className="border-t border-slate-800 p-3">
                        {showSave ? (
                            <div className="flex items-center gap-2">
                                <Input
                                    autoFocus
                                    placeholder="Layout name…"
                                    className="h-7 text-xs bg-slate-900 border-slate-700 text-white flex-1"
                                    value={newName}
                                    onChange={e => setNewName(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setShowSave(false); }}
                                />
                                <Button size="sm" className="h-7 text-xs bg-primary hover:bg-primary/90 text-white px-2" onClick={handleSave} disabled={saving}>
                                    {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Save'}
                                </Button>
                                <button onClick={() => setShowSave(false)} className="text-slate-500 hover:text-white"><X className="h-3.5 w-3.5" /></button>
                            </div>
                        ) : (
                            <Button
                                size="sm"
                                variant="outline"
                                className="w-full h-7 text-xs border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5"
                                onClick={() => setShowSave(true)}
                            >
                                <Plus className="h-3 w-3" />
                                Save current as new layout
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Detail Panel ──
function DetailPanel({ node, onClose, onDeleteAttacker, onConnectAttacker, onDeleteEdge, graphData }: {
    node: Node<GraphNodeData> | null;
    onClose: () => void;
    onDeleteAttacker?: (entityId: string) => void;
    onConnectAttacker?: (entityId: string) => void;
    onDeleteEdge?: (attackerEntityId: string, edgeId: string) => void;
    graphData?: GraphData;
}) {
    if (!node) return null;
    const type = node.type || 'asset';
    const config = typeConfig[type] || typeConfig.asset;
    const data = node.data;
    const Icon = config.icon;

    return (
        <div className="absolute right-3 top-3 w-72 bg-slate-950/95 border border-slate-800 rounded-xl shadow-2xl z-50 backdrop-blur-xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/50">
                <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4" style={{ color: config.text }} />
                    <span className="text-xs font-bold uppercase tracking-wider" style={{ color: config.text }}>
                        {type}
                    </span>
                </div>
                <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
                    <X className="h-4 w-4" />
                </button>
            </div>
            <div className="p-4 space-y-3">
                <div>
                    <p className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">Name</p>
                    <p className="text-sm font-semibold text-white">{data.label}</p>
                </div>
                {data.subtitle && (
                    <div>
                        <p className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">
                            {type === 'asset' ? 'Identifier' : type === 'testcase' ? 'Category' : type === 'finding' ? 'Category' : type === 'attacker' ? 'Point of Presence' : 'Type'}
                        </p>
                        <p className="text-sm text-slate-300">{data.subtitle}</p>
                    </div>
                )}
                {type === 'finding' && data.severity && (
                    <div>
                        <p className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">Severity</p>
                        <Badge
                            className="text-[10px]"
                            style={{
                                color: severityColors[data.severity],
                                background: `${severityColors[data.severity]}22`,
                                borderColor: `${severityColors[data.severity]}44`,
                            }}
                        >
                            {data.severity.toUpperCase()}
                        </Badge>
                    </div>
                )}
                {data.status && (
                    <div>
                        <p className="text-xs text-slate-500 uppercase tracking-wider mb-0.5">Status</p>
                        <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                            {data.status}
                        </Badge>
                    </div>
                )}
                {type === 'asset' && (
                    <div className="flex items-center gap-2">
                        {data.inScope && (
                            <Badge className="text-[9px] bg-cyan-500/20 text-cyan-400 border-cyan-500/30">In Scope</Badge>
                        )}
                        {data.isPwned && (
                            <Badge className="text-[9px] bg-red-500/20 text-red-400 border-red-500/30">Pwned</Badge>
                        )}
                    </div>
                )}
                {type === 'attacker' && data.entityId && (
                    <div className="space-y-3 pt-2 border-t border-slate-800/50">
                        <div className="flex items-center gap-2">
                            <Button
                                size="sm"
                                variant="outline"
                                className="h-6 text-[10px] border-primary/30 text-primary hover:bg-primary/10"
                                onClick={() => onConnectAttacker?.(data.entityId!)}
                            >
                                <Link className="h-3 w-3 mr-1" /> Connect
                            </Button>
                            <Button
                                size="sm"
                                variant="outline"
                                className="h-6 text-[10px] border-red-500/30 text-red-400 hover:bg-red-500/10"
                                onClick={() => onDeleteAttacker?.(data.entityId!)}
                            >
                                <Trash2 className="h-3 w-3 mr-1" /> Delete
                            </Button>
                        </div>
                        {/* Current connections */}
                        {(() => {
                            const attackerNodeId = `attacker-${data.entityId}`;
                            const attackerEdges = graphData?.edges.filter(e => e.source === attackerNodeId) || [];
                            if (attackerEdges.length === 0) return (
                                <p className="text-[10px] text-slate-600 italic">No connections yet</p>
                            );
                            return (
                                <div>
                                    <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Connections ({attackerEdges.length})</p>
                                    <div className="space-y-1 max-h-32 overflow-y-auto">
                                        {attackerEdges.map(edge => {
                                            const targetNode = graphData?.nodes.find(n => n.id === edge.target);
                                            const targetLabel = targetNode?.data.label || edge.target;
                                            const targetType = targetNode?.type || 'unknown';
                                            const targetConfig = typeConfig[targetType] || typeConfig.asset;
                                            return (
                                                <div key={edge.id} className="flex items-center justify-between bg-slate-900/50 rounded px-2 py-1 group">
                                                    <div className="flex items-center gap-1.5 min-w-0">
                                                        <div className="w-1.5 h-1.5 rounded-sm flex-shrink-0" style={{ background: targetConfig.border }} />
                                                        <span className="text-[10px] text-slate-300 truncate">{targetLabel}</span>
                                                    </div>
                                                    <button
                                                        onClick={() => onDeleteEdge?.(data.entityId!, edge.id)}
                                                        className="text-slate-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0 ml-1"
                                                        title="Unlink"
                                                    >
                                                        <X className="h-3 w-3" />
                                                    </button>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })()}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Inner Graph (needs ReactFlowProvider above) ──
function AttackGraphInner({ graphData, engagementId, isFullscreen, onToggleFullscreen, onRefresh, isRefreshing, layouts, onRefreshLayouts }: {
    graphData: GraphData;
    engagementId: string;
    isFullscreen: boolean;
    onToggleFullscreen: () => void;
    onRefresh: () => void;
    isRefreshing: boolean;
    layouts: SavedLayout[];
    onRefreshLayouts: () => void;
}) {
    const [isSaving, setIsSaving] = useState(false);
    const [showAddAttacker, setShowAddAttacker] = useState(false);
    const [showConnectDialog, setShowConnectDialog] = useState<string | null>(null); // attacker entityId
    const [attackerName, setAttackerName] = useState('Threat Actor');
    const [attackerPoP, setAttackerPoP] = useState('External');
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const [selectedNode, setSelectedNode] = useState<Node<GraphNodeData> | null>(null);
    const [showUnlinked, setShowUnlinked] = useState(false);
    const [selectedChain, setSelectedChain] = useState<string>('all');
    const containerRef = useRef<HTMLDivElement>(null);
    const reactFlowInstance = useReactFlow();

    // Determine linked node IDs
    const linkedNodeIds = useMemo(() => {
        const ids = new Set<string>();
        graphData.edges.forEach((e) => {
            ids.add(e.source);
            ids.add(e.target);
        });
        return ids;
    }, [graphData]);

    // Count unlinked
    const unlinkedCount = useMemo(() => {
        return graphData.nodes.filter((n) => !linkedNodeIds.has(`${n.type}-${n.data.entityId}`)).length;
        // Node IDs in the graph are like "asset-xxx", "finding-xxx" etc.
    }, [graphData, linkedNodeIds]);

    const unlinkedCountFromIds = useMemo(() => {
        const allNodeIds = new Set(graphData.nodes.map(n => n.id));
        return graphData.nodes.filter(n => !linkedNodeIds.has(n.id)).length;
    }, [graphData, linkedNodeIds]);

    // Compute connected components (chains) via BFS
    const chains = useMemo(() => {
        const adjacency: Record<string, Set<string>> = {};
        graphData.edges.forEach((e) => {
            if (!adjacency[e.source]) adjacency[e.source] = new Set();
            if (!adjacency[e.target]) adjacency[e.target] = new Set();
            adjacency[e.source].add(e.target);
            adjacency[e.target].add(e.source);
        });

        const visited = new Set<string>();
        const components: Array<{ id: string; name: string; nodeIds: Set<string> }> = [];

        const linkedNodes = graphData.nodes.filter(n => linkedNodeIds.has(n.id));

        for (const startNode of linkedNodes) {
            if (visited.has(startNode.id)) continue;

            const queue = [startNode.id];
            const component = new Set<string>();
            visited.add(startNode.id);

            while (queue.length > 0) {
                const current = queue.shift()!;
                component.add(current);
                const neighbors = adjacency[current];
                if (neighbors) {
                    for (const neighbor of neighbors) {
                        if (!visited.has(neighbor)) {
                            visited.add(neighbor);
                            queue.push(neighbor);
                        }
                    }
                }
            }

            // Name by root test case (or first node)
            const tcNode = graphData.nodes.find(n => component.has(n.id) && n.type === 'testcase');
            const name = tcNode?.data.label || graphData.nodes.find(n => component.has(n.id))?.data.label || 'Unnamed';

            components.push({
                id: `chain-${components.length}`,
                name,
                nodeIds: component,
            });
        }

        return components;
    }, [graphData, linkedNodeIds]);

    // Ref to hold positions for ALL nodes (not just currently visible ones)
    const allPositionsRef = useRef<Record<string, { x: number; y: number }>>({});

    // Convert API data → React Flow nodes/edges with dagre layout or pinned positions
    useEffect(() => {
        if (!graphData || graphData.nodes.length === 0) return;

        const pinnedPos = graphData.pinned_positions;

        // Step 1: Compute positions for ALL linked nodes (full graph layout)
        let allLinkedNodes = graphData.nodes.filter(n => showUnlinked || linkedNodeIds.has(n.id));
        let allLinkedEdges = graphData.edges;
        if (!showUnlinked) {
            const allLinkedNodeIds = new Set(allLinkedNodes.map(n => n.id));
            allLinkedEdges = allLinkedEdges.filter(e => allLinkedNodeIds.has(e.source) && allLinkedNodeIds.has(e.target));
        }

        const allRfNodes: Node[] = allLinkedNodes.map((n) => ({
            id: n.id,
            type: n.type,
            data: n.data,
            position: pinnedPos?.[n.id] ?? allPositionsRef.current[n.id] ?? { x: 0, y: 0 },
        }));

        const allRfEdges: Edge[] = allLinkedEdges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
            type: 'smoothstep' as const,
            animated: true,
            style: { stroke: '#475569', strokeWidth: 1.5 },
            labelStyle: { fill: '#64748b', fontSize: 9, fontWeight: 600 },
            labelBgStyle: { fill: '#0f172a', fillOpacity: 0.9 },
            labelBgPadding: [4, 2] as [number, number],
            markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#475569' },
        }));

        // Compute full layout (or use pinned/existing positions)
        let positionedAllNodes: Node[];
        if (pinnedPos && Object.keys(pinnedPos).length > 0) {
            positionedAllNodes = allRfNodes;
        } else {
            // Check if there are any NEW nodes that don't have positions yet
            const hasNewNodes = allRfNodes.some(n => !allPositionsRef.current[n.id]);
            const hasExistingPositions = Object.keys(allPositionsRef.current).length > 0;

            if (hasNewNodes || !hasExistingPositions) {
                // Run dagre only for a full re-layout (new nodes added or first load)
                const layouted = getLayoutedElements(allRfNodes, allRfEdges, 'LR');
                positionedAllNodes = layouted.nodes;
            } else {
                // Reuse existing positions — just adding/removing edges shouldn't re-layout
                positionedAllNodes = allRfNodes;
            }
        }

        // Store ALL positions in ref
        positionedAllNodes.forEach(n => {
            allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y };
        });

        // Step 2: Filter to selected chain for display
        let displayNodes = positionedAllNodes;
        let displayEdges = allRfEdges;

        if (selectedChain !== 'all') {
            const chain = chains.find(c => c.id === selectedChain);
            if (chain) {
                displayNodes = displayNodes.filter(n => chain.nodeIds.has(n.id));
                displayEdges = displayEdges.filter(e => chain.nodeIds.has(e.source) && chain.nodeIds.has(e.target));
            }
        }

        if (displayNodes.length === 0) {
            setNodes([]);
            setEdges([]);
            return;
        }

        setNodes(displayNodes);
        setEdges(displayEdges);

        // Only fitView on first load or when dagre actually ran (new nodes)
        const hadNewNodes = allRfNodes.some(n => !allPositionsRef.current[n.id]);
        if (hadNewNodes || !Object.keys(allPositionsRef.current).length) {
            // Store positions AFTER dagre ran
            positionedAllNodes.forEach(n => {
                allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y };
            });
            setTimeout(() => {
                reactFlowInstance.fitView({ padding: 0.2 });
            }, 50);
        }
    }, [graphData, showUnlinked, selectedChain, chains, linkedNodeIds, setNodes, setEdges, reactFlowInstance]);

    const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
        setSelectedNode(node as Node<GraphNodeData>);
    }, []);

    // Highlight edges connected to selected node
    useEffect(() => {
        setEdges(currentEdges => currentEdges.map(edge => {
            if (!selectedNode) {
                // No selection — default styling
                return { ...edge, style: { stroke: '#475569', strokeWidth: 1.5 }, animated: true, labelStyle: { fill: '#64748b', fontSize: 9, fontWeight: 600 } };
            }
            const isConnected = edge.source === selectedNode.id || edge.target === selectedNode.id;
            if (isConnected) {
                // Get the color from the selected node's type
                const nodeConfig = typeConfig[selectedNode.type || 'asset'];
                return { ...edge, style: { stroke: nodeConfig?.border || '#818cf8', strokeWidth: 2.5 }, animated: true, labelStyle: { fill: '#e2e8f0', fontSize: 9, fontWeight: 700 }, zIndex: 10 };
            }
            // Dim unrelated edges
            return { ...edge, style: { stroke: '#1e293b', strokeWidth: 1 }, animated: false, labelStyle: { fill: '#334155', fontSize: 9, fontWeight: 600 }, zIndex: 0 };
        }));
    }, [selectedNode, setEdges]);

    // Handle drawn edges from attacker nodes
    const onConnect = useCallback(async (connection: Connection) => {
        if (!connection.source || !connection.target) return;
        // Only persist edges from attacker nodes
        if (connection.source.startsWith('attacker-')) {
            // Check for duplicate edge
            const alreadyExists = edges.some(e => e.source === connection.source && e.target === connection.target);
            if (alreadyExists) {
                toast.warning('Connection already exists');
                return;
            }
            const attackerEntityId = connection.source.replace('attacker-', '');
            const targetType = connection.target.split('-')[0];
            try {
                // Snapshot current positions before refresh so nodes don't move
                nodes.forEach(n => {
                    allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y };
                });
                await api.post(`/engagements/${engagementId}/attack-graph/attacker/${attackerEntityId}/edge`, {
                    target_node_id: connection.target,
                    target_node_type: targetType,
                });
                toast.success('Edge created');
                onRefresh();
            } catch (e) {
                toast.error('Failed to create edge');
            }
        }
    }, [engagementId, onRefresh]);

    const resetLayout = useCallback(async () => {
        // Unpin from server
        try {
            await api.delete(`/engagements/${engagementId}/attack-graph/layout`);
        } catch { /* ignore if no layout saved */ }
        const layouted = getLayoutedElements(nodes, edges, 'LR');
        setNodes(layouted.nodes);
        setTimeout(() => {
            reactFlowInstance.fitView({ padding: 0.2 });
        }, 50);
        onRefresh();
        toast.success('Layout reset to auto-layout');
    }, [nodes, edges, setNodes, reactFlowInstance, engagementId, onRefresh]);

    // ── Export to draw.io ──
    const handleExportDrawio = useCallback(() => {
        // Escape XML special characters
        const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

        const NODE_W = 240;
        const NODE_H = 80;
        let cellId = 2; // 0 and 1 are reserved for root and default parent in mxGraphModel
        const nodeIdMap: Record<string, number> = {};

        // Build cells for nodes — use light colors that read well on draw.io's white background
        const drawioColors: Record<string, { bg: string; border: string; text: string }> = {
            asset: { bg: '#dbeafe', border: '#3b82f6', text: '#1e3a5f' },    // light blue
            testcase: { bg: '#fef3c7', border: '#f59e0b', text: '#78350f' },    // light amber
            finding: { bg: '#fee2e2', border: '#ef4444', text: '#7f1d1d' },    // light red
            cleanup: { bg: '#ecfccb', border: '#84cc16', text: '#365314' },    // light lime
            attacker: { bg: '#f3e8ff', border: '#a855f7', text: '#581c87' },    // light purple
        };
        const drawioSeverityColors: Record<string, { bg: string; border: string }> = {
            critical: { bg: '#fee2e2', border: '#dc2626' },
            high: { bg: '#ffedd5', border: '#ea580c' },
            medium: { bg: '#fef9c3', border: '#ca8a04' },
            low: { bg: '#dbeafe', border: '#2563eb' },
            info: { bg: '#f3f4f6', border: '#6b7280' },
        };

        const nodeCells = nodes.map((node) => {
            const id = cellId++;
            nodeIdMap[node.id] = id;
            const nodeData = node.data as GraphNodeData;
            const label = nodeData.label || node.id;
            const subtitle = nodeData.subtitle || '';
            const severity = nodeData.severity?.toLowerCase() || '';
            const nodeType = node.type || 'asset';

            const colors = drawioColors[nodeType] || drawioColors.asset;
            // For findings, tint by severity
            let bgColor = colors.bg;
            let borderColor = colors.border;
            const textColor = colors.text;
            if (nodeType === 'finding' && severity && drawioSeverityColors[severity]) {
                bgColor = drawioSeverityColors[severity].bg;
                borderColor = drawioSeverityColors[severity].border;
            }

            const displayLabel = subtitle ? `${esc(label)}&#xa;${esc(subtitle)}` : esc(label);

            const x = Math.round(node.position.x);
            const y = Math.round(node.position.y);

            return `      <mxCell id="${id}" value="${displayLabel}" style="rounded=1;whiteSpace=wrap;html=0;fillColor=${bgColor};strokeColor=${borderColor};fontColor=${textColor};fontSize=11;fontFamily=Inter;strokeWidth=2;arcSize=12;spacingTop=4;spacingBottom=4;" vertex="1" parent="1">
        <mxGeometry x="${x}" y="${y}" width="${NODE_W}" height="${NODE_H}" as="geometry" />
      </mxCell>`;
        });

        // Build cells for edges
        const edgeCells = edges.map((edge) => {
            const id = cellId++;
            const sourceId = nodeIdMap[edge.source];
            const targetId = nodeIdMap[edge.target];
            if (sourceId === undefined || targetId === undefined) return '';

            const label = edge.label ? ` value="${esc(String(edge.label))}"` : '';

            return `      <mxCell id="${id}"${label} style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#475569;strokeWidth=1.5;fontColor=#94a3b8;fontSize=9;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" source="${sourceId}" target="${targetId}" parent="1">
        <mxGeometry relative="1" as="geometry" />
      </mxCell>`;
        }).filter(Boolean);

        const xml = `<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" modified="${new Date().toISOString()}" type="device">
  <diagram id="attack-graph" name="Attack Graph">
    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
${nodeCells.join('\n')}
${edgeCells.join('\n')}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>`;

        const blob = new Blob([xml], { type: 'application/xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'attack-graph.drawio';
        a.click();
        URL.revokeObjectURL(url);
        toast.success('Exported to draw.io format');
    }, [nodes, edges]);

    const pinLayout = useCallback(async () => {
        setIsSaving(true);
        try {
            // Start with all known positions (covers nodes not currently visible due to chain filter)
            const positions: Record<string, { x: number; y: number }> = {
                ...allPositionsRef.current,
            };
            // Override with current visible node positions (may have been dragged)
            nodes.forEach((n) => {
                positions[n.id] = { x: n.position.x, y: n.position.y };
            });
            // Update the ref too
            Object.assign(allPositionsRef.current, positions);
            await api.put(`/engagements/${engagementId}/attack-graph/layout`, { positions });
            toast.success('Layout pinned for all users');
            onRefresh();
        } catch (e) {
            toast.error('Failed to pin layout');
            console.error('Failed to pin layout', e);
        } finally {
            setIsSaving(false);
        }
    }, [nodes, engagementId, onRefresh]);

    const POP_OPTIONS = ['External', 'Internal LAN', 'VPN', 'Wireless', 'Cloud', 'Physical', 'Supply Chain'];

    const handleAddAttacker = useCallback(async () => {
        try {
            await api.post(`/engagements/${engagementId}/attack-graph/attacker`, {
                name: attackerName,
                point_of_presence: attackerPoP,
            });
            toast.success('Attacker node added');
            setShowAddAttacker(false);
            setAttackerName('Threat Actor');
            setAttackerPoP('External');
            // Snapshot positions so existing nodes don't jump
            nodes.forEach(n => { allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y }; });
            onRefresh();
        } catch (e) {
            toast.error('Failed to add attacker node');
        }
    }, [engagementId, attackerName, attackerPoP, onRefresh]);

    const handleDeleteAttacker = useCallback(async (entityId: string) => {
        try {
            await api.delete(`/engagements/${engagementId}/attack-graph/attacker/${entityId}`);
            toast.success('Attacker node removed');
            setSelectedNode(null);
            const attackerNodeId = `attacker-${entityId}`;
            delete allPositionsRef.current[attackerNodeId];
            nodes.forEach(n => { allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y }; });
            onRefresh();
        } catch (e) {
            toast.error('Failed to delete attacker node');
        }
    }, [engagementId, onRefresh, nodes]);

    const handleDeleteEdge = useCallback(async (attackerEntityId: string, edgeId: string) => {
        try {
            await api.delete(`/engagements/${engagementId}/attack-graph/attacker/${attackerEntityId}/edge/${edgeId}`);
            toast.success('Connection removed');
            nodes.forEach(n => { allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y }; });
            onRefresh();
        } catch (e) {
            toast.error('Failed to remove connection');
        }
    }, [engagementId, onRefresh, nodes]);

    const handleConnectAttacker = useCallback(async (attackerEntityId: string, targetNodeId: string, targetNodeType: string) => {
        try {
            await api.post(`/engagements/${engagementId}/attack-graph/attacker/${attackerEntityId}/edge`, {
                target_node_id: targetNodeId,
                target_node_type: targetNodeType,
            });
            toast.success('Edge created');
            setShowConnectDialog(null);
            // Snapshot positions so existing nodes don't jump
            nodes.forEach(n => { allPositionsRef.current[n.id] = { x: n.position.x, y: n.position.y }; });
            onRefresh();
        } catch (e) {
            toast.error('Failed to create edge');
        }
    }, [engagementId, onRefresh]);

    // Counts for the legend
    const counts = useMemo(() => {
        if (!graphData) return { assets: 0, testcases: 0, findings: 0, cleanup: 0, attackers: 0 };
        return {
            assets: graphData.nodes.filter((n) => n.type === 'asset').length,
            testcases: graphData.nodes.filter((n) => n.type === 'testcase').length,
            findings: graphData.nodes.filter((n) => n.type === 'finding').length,
            cleanup: graphData.nodes.filter((n) => n.type === 'cleanup').length,
            attackers: graphData.nodes.filter((n) => n.type === 'attacker').length,
        };
    }, [graphData, showUnlinked, linkedNodeIds]);

    if (nodes.length === 0 && !showUnlinked) {
        return (
            <div className="flex items-center justify-center h-full bg-slate-950/50 rounded-xl border border-dashed border-slate-700">
                <div className="text-center">
                    <LayoutDashboard className="h-10 w-10 text-slate-700 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">No linked entities to graph</p>
                    <p className="text-xs text-slate-600 mt-1">Link assets to findings or test cases to see connections.</p>
                    {unlinkedCountFromIds > 0 && (
                        <Button
                            size="sm"
                            variant="outline"
                            className="mt-3 h-7 text-xs border-slate-700 text-slate-400 hover:bg-slate-800"
                            onClick={() => setShowUnlinked(true)}
                        >
                            <Eye className="h-3 w-3 mr-1" /> Show {unlinkedCountFromIds} unlinked items
                        </Button>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div ref={containerRef} className="relative w-full h-full">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onConnect={onConnect}
                onPaneClick={() => setSelectedNode(null)}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.1}
                maxZoom={2}
                proOptions={{ hideAttribution: true }}
                style={{ background: 'hsl(var(--background))' }}
            >
                <Background color="hsl(var(--border))" gap={20} size={1} />
                <Controls
                    position="bottom-left"
                    className="!bg-slate-900 !border-slate-700 !rounded-lg !shadow-xl [&>button]:!bg-slate-800 [&>button]:!border-slate-700 [&>button]:!text-slate-400 [&>button:hover]:!bg-slate-700 [&>button:hover]:!text-white"
                />
                <MiniMap
                    nodeColor={(node) => {
                        const config = typeConfig[node.type || 'asset'];
                        return config?.border || '#475569';
                    }}
                    maskColor="hsl(var(--background) / 0.8)"
                    className="!bg-slate-900/80 !border-slate-700 !rounded-lg"
                    pannable
                    zoomable
                />
                <Panel position="top-left">
                    <div className="flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border border-slate-800 rounded-lg px-3 py-2 shadow-xl">
                        {Object.entries(typeConfig).map(([type, cfg]) => {
                            const countKey = type === 'testcase' ? 'testcases' : type === 'finding' ? 'findings' : type === 'asset' ? 'assets' : type === 'attacker' ? 'attackers' : 'cleanup';
                            const count = counts[countKey as keyof typeof counts];
                            return (
                                <div key={type} className="flex items-center gap-1.5">
                                    <div className="w-2.5 h-2.5 rounded-sm" style={{ background: cfg.border }} />
                                    <span className="text-[10px] text-slate-400 capitalize">{type === 'testcase' ? 'Tests' : type + 's'}</span>
                                    <span className="text-[10px] font-bold text-slate-500">{count}</span>
                                </div>
                            );
                        })}
                    </div>
                </Panel>
                <Panel position="top-right">
                    <div className="flex items-center gap-1">
                        {/* Icon-only action buttons */}
                        <Button
                            size="icon"
                            variant="outline"
                            className="h-7 w-7 border-primary/50 bg-slate-900/90 text-primary hover:bg-primary/10 backdrop-blur-xl"
                            onClick={() => setShowAddAttacker(true)}
                            title="Add attacker node"
                        >
                            <Crosshair className="h-3.5 w-3.5" />
                        </Button>
                        {/* Layouts popover */}
                        <LayoutsPopover
                            engagementId={engagementId}
                            layouts={layouts}
                            onRefreshLayouts={onRefreshLayouts}
                            onRefreshGraph={onRefresh}
                            getPositions={() => {
                                const positions: Record<string, { x: number; y: number }> = { ...allPositionsRef.current };
                                nodes.forEach(n => { positions[n.id] = { x: n.position.x, y: n.position.y }; });
                                return positions;
                            }}
                        />
                        <Button
                            size="icon"
                            variant="outline"
                            className={`h-7 w-7 border-slate-700 bg-slate-900/90 backdrop-blur-xl ${graphData.pinned_positions ? 'text-amber-400 border-amber-500/50' : 'text-slate-300 hover:bg-slate-800'}`}
                            onClick={pinLayout}
                            disabled={isSaving}
                            title={graphData.pinned_positions ? 'Update pinned layout' : 'Pin current layout for all users'}
                        >
                            <span className="text-sm">📌</span>
                        </Button>
                        <Button
                            size="icon"
                            variant="outline"
                            className={`h-7 w-7 border-slate-700 bg-slate-900/90 backdrop-blur-xl ${showUnlinked ? 'text-cyan-400 border-cyan-500/50' : 'text-slate-300 hover:bg-slate-800'}`}
                            onClick={() => setShowUnlinked(!showUnlinked)}
                            title={showUnlinked ? `Hide unlinked items (${unlinkedCountFromIds})` : `Show ${unlinkedCountFromIds} unlinked items`}
                        >
                            {showUnlinked ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </Button>
                        <Button
                            size="icon"
                            variant="outline"
                            className="h-7 w-7 border-slate-700 bg-slate-900/90 text-slate-300 hover:bg-slate-800 backdrop-blur-xl"
                            onClick={onRefresh}
                            disabled={isRefreshing}
                            title="Refresh graph data"
                        >
                            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button
                            size="icon"
                            variant="outline"
                            className="h-7 w-7 border-slate-700 bg-slate-900/90 text-slate-300 hover:bg-slate-800 backdrop-blur-xl"
                            onClick={resetLayout}
                            title="Reset layout to auto-layout"
                        >
                            <LayoutDashboard className="h-3.5 w-3.5" />
                        </Button>

                        <Button
                            size="icon"
                            variant="outline"
                            className="h-7 w-7 border-slate-700 bg-slate-900/90 text-slate-300 hover:bg-slate-800 backdrop-blur-xl"
                            onClick={handleExportDrawio}
                            title="Export to draw.io"
                        >
                            <Download className="h-3.5 w-3.5" />
                        </Button>

                        {/* Divider */}
                        <div className="w-px h-5 bg-slate-700 mx-0.5" />

                        {/* Chain dropdown */}
                        {chains.length >= 1 && (
                            <Select value={selectedChain} onValueChange={setSelectedChain}>
                                <SelectTrigger className="h-7 w-[180px] text-xs border-slate-700 bg-slate-900/90 text-slate-300 backdrop-blur-xl">
                                    <SelectValue placeholder="All Chains" />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-700" container={containerRef.current ?? undefined}>
                                    <SelectItem value="all" className="text-xs text-slate-300">All Chains ({chains.length})</SelectItem>
                                    {chains.map((chain) => (
                                        <SelectItem key={chain.id} value={chain.id} className="text-xs text-slate-300">
                                            {chain.name} ({chain.nodeIds.size})
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        )}

                        {/* Fullscreen */}
                        <Button
                            size="icon"
                            variant="outline"
                            className="h-7 w-7 border-slate-700 bg-slate-900/90 text-slate-300 hover:bg-slate-800 backdrop-blur-xl"
                            onClick={onToggleFullscreen}
                            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                        >
                            {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
                        </Button>
                    </div>
                </Panel>
            </ReactFlow>

            <DetailPanel
                node={selectedNode}
                onClose={() => setSelectedNode(null)}
                onDeleteAttacker={handleDeleteAttacker}
                onConnectAttacker={(entityId) => setShowConnectDialog(entityId)}
                onDeleteEdge={handleDeleteEdge}
                graphData={graphData}
            />

            {/* Add Attacker Dialog */}
            {showAddAttacker && (
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
                    <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 w-80 shadow-2xl space-y-4">
                        <div className="flex items-center gap-2">
                            <Crosshair className="h-5 w-5 text-primary" />
                            <h3 className="text-sm font-bold text-white">Add Attacker Node</h3>
                        </div>
                        <div>
                            <label className="text-xs text-slate-400 mb-1 block">Name</label>
                            <input
                                className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-white focus:outline-none focus:border-primary"
                                value={attackerName}
                                onChange={(e) => setAttackerName(e.target.value)}
                                placeholder="Threat Actor"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-slate-400 mb-1 block">Point of Presence</label>
                            <Select value={attackerPoP} onValueChange={setAttackerPoP}>
                                <SelectTrigger className="w-full bg-slate-800 border-slate-700 text-sm text-white">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-700" container={containerRef.current ?? undefined}>
                                    {POP_OPTIONS.map((opt) => (
                                        <SelectItem key={opt} value={opt} className="text-sm text-slate-300">{opt}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="flex justify-end gap-2">
                            <Button size="sm" variant="ghost" className="text-slate-400" onClick={() => setShowAddAttacker(false)}>Cancel</Button>
                            <Button size="sm" className="bg-primary hover:bg-primary/90 text-white" onClick={handleAddAttacker}>Add</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Connect Attacker Dialog */}
            {showConnectDialog && (
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
                    <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 w-80 shadow-2xl space-y-3">
                        <div className="flex items-center gap-2">
                            <Link className="h-5 w-5 text-primary" />
                            <h3 className="text-sm font-bold text-white">Connect to Test Case</h3>
                        </div>
                        <div className="max-h-60 overflow-auto space-y-1">
                            {graphData.nodes.filter(n => n.type === 'testcase').map((tc) => (
                                <button
                                    key={tc.id}
                                    className="w-full text-left px-3 py-2 rounded-md text-sm text-slate-300 hover:bg-primary/10 hover:text-primary/80 transition-colors border border-transparent hover:border-primary/30"
                                    onClick={() => handleConnectAttacker(showConnectDialog, tc.id, 'testcase')}
                                >
                                    {tc.data.label}
                                </button>
                            ))}
                            {graphData.nodes.filter(n => n.type === 'testcase').length === 0 && (
                                <p className="text-xs text-slate-500 text-center py-4">No test cases available</p>
                            )}
                        </div>
                        <div className="flex justify-end">
                            <Button size="sm" variant="ghost" className="text-slate-400" onClick={() => setShowConnectDialog(null)}>Cancel</Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Main Component ──
interface AttackGraphProps {
    engagementId: string;
}

export function AttackGraph({ engagementId }: AttackGraphProps) {
    const { data: graphData, isLoading, error, refetch, isFetching } = useQuery<GraphData>({
        queryKey: ['attack-graph', engagementId],
        queryFn: async () => {
            const res = await api.get(`/engagements/${engagementId}/attack-graph`);
            return res.data;
        },
    });

    const { data: layouts = [], refetch: refetchLayouts } = useGraphLayouts(engagementId);

    const [isFullscreen, setIsFullscreen] = useState(false);

    // Listen for real-time layout pin/unpin events from other users
    useCollaboration({
        resourceType: 'engagement',
        resourceId: engagementId,
        onMessage: useCallback((data: any) => {
            if (data.type === 'graph_layout_pinned') {
                toast.info(`${data.username || 'A user'} pinned the graph layout`);
                refetch();
            } else if (data.type === 'graph_layout_unpinned') {
                toast.info(`${data.username || 'A user'} reset the graph layout`);
                refetch();
            } else if (data.type === 'graph_attacker_changed') {
                toast.info(`${data.username || 'A user'} modified the attack graph`);
                refetch();
            } else if (data.type === 'graph_layout_activated') {
                toast.info(`${data.username || 'A user'} loaded layout "${data.layout_name || ''}"`);
                refetch();
                refetchLayouts();
            } else if (data.type === 'graph_layout_saved' || data.type === 'graph_layout_deleted') {
                refetchLayouts();
            }
        }, [refetch, refetchLayouts]),
    });

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-[500px] bg-slate-950/50 rounded-xl border border-slate-800">
                <div className="text-center">
                    <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mx-auto mb-3" />
                    <p className="text-sm text-slate-400">Building attack graph…</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-[300px] bg-slate-950/50 rounded-xl border border-slate-800">
                <p className="text-sm text-red-400">Failed to load attack graph.</p>
            </div>
        );
    }

    if (!graphData || graphData.nodes.length === 0) {
        return (
            <div className="flex items-center justify-center h-[300px] bg-slate-950/50 rounded-xl border border-dashed border-slate-700">
                <div className="text-center">
                    <LayoutDashboard className="h-10 w-10 text-slate-700 mx-auto mb-3" />
                    <p className="text-sm text-slate-500">No entities to graph</p>
                    <p className="text-xs text-slate-600 mt-1">Add assets, test cases, or findings to see the attack graph.</p>
                </div>
            </div>
        );
    }

    const graphContent = (
        <ReactFlowProvider>
            <AttackGraphInner
                graphData={graphData}
                engagementId={engagementId}
                isFullscreen={isFullscreen}
                onToggleFullscreen={() => setIsFullscreen(!isFullscreen)}
                onRefresh={() => refetch()}
                isRefreshing={isFetching}
                layouts={layouts}
                onRefreshLayouts={() => refetchLayouts()}
            />
        </ReactFlowProvider>
    );

    if (isFullscreen) {
        return createPortal(
            <div className="fixed inset-0 z-[9999] bg-slate-950">
                {graphContent}
            </div>,
            document.body
        );
    }

    return (
        <div className="relative h-[600px] bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
            {graphContent}
        </div>
    );
}
