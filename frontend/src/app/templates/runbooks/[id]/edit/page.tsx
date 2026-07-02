/**
 * templates/runbooks/[id]/edit/page.tsx — Runbook Editor
 *
 * Hierarchical tree builder for runbooks (ordered collections of
 * test-case templates). Two-panel layout:
 *
 * **Left panel** — name, description, and the template tree.
 *   Tree nodes are draggable (native HTML drag-and-drop with
 *   before / inside / after drop zones). Each node shows a grip
 *   handle, expand/collapse chevron, title, category badge, and
 *   action buttons (indent ▸, outdent ◂, delete).
 *
 * **Right panel** — template palette. Searchable list of all
 *   test-case templates. Click adds a template as a root node;
 *   already-used templates shown with a green check mark and
 *   disabled.
 *
 * Tree helpers: `flattenTree`, `deepCloneTree`, `isDescendant`,
 * `extractNode`, `insertNode`. Sort-order renumbered on save.
 *
 * Sub-components: `TreeNodeList`, `DraggableTreeNode`.
 */
'use client';

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import { useTestCaseTemplates, TestCaseTemplate } from '@/lib/hooks/use-testcase-templates';
import { useRunbook, useCreateRunbook, useUpdateRunbook, RunbookItemCreate, RunbookItemTemplate } from '@/lib/hooks/use-runbooks';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import {
    ArrowLeft,
    Save,
    Loader2,
    GitBranch,
    Plus,
    Trash2,
    Search,
    ChevronRight,
    ChevronDown,
    GripVertical,
    ArrowRight,
    ArrowLeftIcon,
    CheckCircle2,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────
interface TreeNode {
    temp_key: string;
    template_id: string;
    // Snapshot fields used for rendering — both the full TestCaseTemplate
    // (from the templates list) and the embedded RunbookItemTemplate
    // (from a saved runbook) satisfy this shape.
    template: RunbookItemTemplate | null;
    parent_temp_key: string | null;
    sort_order: number;
    children: TreeNode[];
    expanded: boolean;
}

type DropPosition = 'before' | 'inside' | 'after';

// ─── Tree helpers ─────────────────────────────────────────────────
function flattenTree(nodes: TreeNode[]): RunbookItemCreate[] {
    const items: RunbookItemCreate[] = [];
    const walk = (nodeList: TreeNode[]) => {
        for (const node of nodeList) {
            items.push({
                template_id: node.template_id,
                temp_key: node.temp_key,
                parent_temp_key: node.parent_temp_key,
                sort_order: node.sort_order,
            });
            walk(node.children);
        }
    };
    walk(nodes);
    return items;
}

function deepCloneTree(nodes: TreeNode[]): TreeNode[] {
    return nodes.map(n => ({ ...n, children: deepCloneTree(n.children) }));
}

/** Check if `possibleDescendantKey` is a descendant of `ancestorKey` in the tree */
function isDescendant(nodes: TreeNode[], ancestorKey: string, possibleDescendantKey: string): boolean {
    const findNode = (list: TreeNode[], key: string): TreeNode | null => {
        for (const n of list) {
            if (n.temp_key === key) return n;
            const found = findNode(n.children, key);
            if (found) return found;
        }
        return null;
    };
    const ancestor = findNode(nodes, ancestorKey);
    if (!ancestor) return false;
    const check = (node: TreeNode): boolean => {
        if (node.temp_key === possibleDescendantKey) return true;
        return node.children.some(check);
    };
    return ancestor.children.some(check);
}

/** Remove a node from the tree by key, returns [newTree, removedNode] */
function extractNode(nodes: TreeNode[], key: string): [TreeNode[], TreeNode | null] {
    let removed: TreeNode | null = null;
    const filter = (list: TreeNode[]): TreeNode[] => {
        return list.filter(n => {
            if (n.temp_key === key) {
                removed = n;
                return false;
            }
            n.children = filter(n.children);
            return true;
        });
    };
    const newTree = filter(deepCloneTree(nodes));
    return [newTree, removed];
}

/** Insert a node into the tree at a specific location */
function insertNode(
    nodes: TreeNode[],
    nodeToInsert: TreeNode,
    targetKey: string,
    position: DropPosition,
    targetParentKey: string | null
): TreeNode[] {
    if (position === 'inside') {
        // Make child of target
        const insertInto = (list: TreeNode[]): boolean => {
            for (const n of list) {
                if (n.temp_key === targetKey) {
                    nodeToInsert.parent_temp_key = n.temp_key;
                    nodeToInsert.sort_order = n.children.length;
                    n.children.push(nodeToInsert);
                    n.expanded = true;
                    return true;
                }
                if (insertInto(n.children)) return true;
            }
            return false;
        };
        insertInto(nodes);
    } else {
        // Insert before or after the target in its parent list
        const insertInList = (list: TreeNode[]): boolean => {
            for (let i = 0; i < list.length; i++) {
                if (list[i].temp_key === targetKey) {
                    const idx = position === 'before' ? i : i + 1;
                    nodeToInsert.parent_temp_key = targetParentKey;
                    list.splice(idx, 0, nodeToInsert);
                    return true;
                }
                if (insertInList(list[i].children)) return true;
            }
            return false;
        };
        insertInList(nodes);
    }
    return nodes;
}

let globalKeyCounter = 0;
function nextKey() {
    return `tk_${++globalKeyCounter}_${Date.now()}`;
}

const EMPTY_TEMPLATES: TestCaseTemplate[] = [];

// ═══════════════════════════════════════════════════════════════════
// Runbook Editor Page
// ═══════════════════════════════════════════════════════════════════
export default function RunbookEditorPage() {
    const router = useRouter();
    const params = useParams();
    const { user } = useAuthStore();
    const runbookId = params?.id as string;
    const isNew = runbookId === 'new';
    const canManage = user?.role === UserRole.ADMIN || user?.role === UserRole.TEAM_LEAD;

    // ── Data ──
    const { data: existingRunbook, isLoading: rbLoading } = useRunbook(isNew ? undefined : runbookId);

    const isOwner = !!existingRunbook && existingRunbook.created_by === user?.id;
    const isDraft = existingRunbook?.status === 'DRAFT';
    const isSubmitted = existingRunbook?.status === 'SUBMITTED';
    const isPublished = existingRunbook?.status === 'PUBLISHED';
    const allowedToEdit = isNew
        || (isDraft && (isOwner || canManage))
        || (isPublished && canManage);
    const { data: rawTemplates, isLoading: tmplLoading } = useTestCaseTemplates();
    const templates = rawTemplates ?? EMPTY_TEMPLATES;
    const createRunbook = useCreateRunbook();
    const updateRunbook = useUpdateRunbook();

    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [runbookType, setRunbookType] = useState('');
    const [tree, setTree] = useState<TreeNode[]>([]);
    const [tmplSearch, setTmplSearch] = useState('');
    const [saving, setSaving] = useState(false);

    // ── Configurable runbook types ──
    const { data: runbookTypes = [] } = useConfigurableTypes('runbook');

    // ── Drag state (use refs to avoid re-render storms) ──
    const [draggedKey, setDraggedKey] = useState<string | null>(null);
    const [dropTarget, setDropTarget] = useState<{ key: string; position: DropPosition } | null>(null);
    const dropTargetRef = useRef<{ key: string; position: DropPosition } | null>(null);

    const handleDropTargetChange = useCallback((target: { key: string; position: DropPosition } | null) => {
        const prev = dropTargetRef.current;
        if (prev?.key === target?.key && prev?.position === target?.position) return;
        dropTargetRef.current = target;
        setDropTarget(target);
    }, []);

    const handleDragEnd = useCallback(() => {
        setDraggedKey(null);
        dropTargetRef.current = null;
        setDropTarget(null);
    }, []);

    // ── Initialize from existing ──
    const hasInitialized = useRef(false);
    useEffect(() => {
        if (hasInitialized.current) return;
        if (existingRunbook && !isNew) {
            hasInitialized.current = true;
            setName(existingRunbook.name);
            setDescription(existingRunbook.description || '');
            setRunbookType(existingRunbook.runbook_type || '');

            const itemMap = new Map<string, TreeNode>();
            const roots: TreeNode[] = [];
            const idToKey = new Map<string, string>();
            for (const item of existingRunbook.items) {
                const key = nextKey();
                idToKey.set(item.id, key);
            }
            for (const item of existingRunbook.items) {
                const key = idToKey.get(item.id)!;
                const parentKey = item.parent_id ? idToKey.get(item.parent_id) || null : null;
                const tmpl = templates.find(t => t.id === item.template_id) || null;
                const node: TreeNode = {
                    temp_key: key,
                    template_id: item.template_id,
                    template: item.template ?? tmpl,
                    parent_temp_key: parentKey,
                    sort_order: item.sort_order,
                    children: [],
                    expanded: true,
                };
                itemMap.set(key, node);
            }
            for (const [, node] of itemMap) {
                if (node.parent_temp_key && itemMap.has(node.parent_temp_key)) {
                    itemMap.get(node.parent_temp_key)!.children.push(node);
                } else {
                    roots.push(node);
                }
            }
            const sortAll = (nodes: TreeNode[]) => {
                nodes.sort((a, b) => a.sort_order - b.sort_order);
                nodes.forEach(n => sortAll(n.children));
            };
            sortAll(roots);
            setTree(roots);
        }
    }, [existingRunbook, isNew, templates]);

    // ── Collect template IDs already in the tree ──
    const usedTemplateIds = useMemo(() => {
        const ids = new Set<string>();
        const walk = (nodes: TreeNode[]) => {
            for (const n of nodes) {
                ids.add(n.template_id);
                walk(n.children);
            }
        };
        walk(tree);
        return ids;
    }, [tree]);

    // ── Filtered templates ──
    const filteredTemplates = useMemo(() =>
        templates.filter(t =>
            t.title.toLowerCase().includes(tmplSearch.toLowerCase()) ||
            t.category.toLowerCase().includes(tmplSearch.toLowerCase())
        ), [templates, tmplSearch]
    );

    // ── Add template to tree (as root) ──
    const addTemplateToTree = useCallback((template: TestCaseTemplate) => {
        const node: TreeNode = {
            temp_key: nextKey(),
            template_id: template.id,
            template: template,
            parent_temp_key: null,
            sort_order: tree.length,
            children: [],
            expanded: true,
        };
        setTree(prev => [...prev, node]);
    }, [tree.length]);

    // ── Remove node from tree ──
    const removeNode = useCallback((targetKey: string) => {
        const removeFromList = (nodes: TreeNode[]): TreeNode[] => {
            return nodes.filter(n => {
                if (n.temp_key === targetKey) return false;
                n.children = removeFromList(n.children);
                return true;
            });
        };
        setTree(prev => removeFromList(deepCloneTree(prev)));
    }, []);

    // ── Indent (make child of previous sibling) ──
    const indentNode = useCallback((targetKey: string) => {
        setTree(prev => {
            const newTree = deepCloneTree(prev);
            const findAndIndent = (nodes: TreeNode[]): boolean => {
                for (let i = 0; i < nodes.length; i++) {
                    if (nodes[i].temp_key === targetKey && i > 0) {
                        const node = nodes.splice(i, 1)[0];
                        node.parent_temp_key = nodes[i - 1].temp_key;
                        node.sort_order = nodes[i - 1].children.length;
                        nodes[i - 1].children.push(node);
                        nodes[i - 1].expanded = true;
                        return true;
                    }
                    if (findAndIndent(nodes[i].children)) return true;
                }
                return false;
            };
            findAndIndent(newTree);
            return newTree;
        });
    }, []);

    // ── Outdent (move to parent's level) ──
    const outdentNode = useCallback((targetKey: string) => {
        setTree(prev => {
            const newTree = deepCloneTree(prev);
            const findAndOutdent = (nodes: TreeNode[], parentList: TreeNode[] | null, parentIndex: number | null): boolean => {
                for (let i = 0; i < nodes.length; i++) {
                    if (nodes[i].temp_key === targetKey && parentList !== null && parentIndex !== null) {
                        const node = nodes.splice(i, 1)[0];
                        node.parent_temp_key = parentList[parentIndex].parent_temp_key;
                        node.sort_order = parentIndex + 1;
                        parentList.splice(parentIndex + 1, 0, node);
                        return true;
                    }
                    if (findAndOutdent(nodes[i].children, nodes, i)) return true;
                }
                return false;
            };
            findAndOutdent(newTree, null, null);
            return newTree;
        });
    }, []);

    // ── Toggle expand ──
    const toggleExpand = useCallback((targetKey: string) => {
        setTree(prev => {
            const newTree = deepCloneTree(prev);
            const findAndToggle = (nodes: TreeNode[]): boolean => {
                for (const node of nodes) {
                    if (node.temp_key === targetKey) {
                        node.expanded = !node.expanded;
                        return true;
                    }
                    if (findAndToggle(node.children)) return true;
                }
                return false;
            };
            findAndToggle(newTree);
            return newTree;
        });
    }, []);

    // ── Drag & Drop: move node ──
    const moveNode = useCallback((sourceKey: string, targetKey: string, position: DropPosition) => {
        setTree(prev => {
            // Don't drop onto itself
            if (sourceKey === targetKey) return prev;
            // Don't drop a parent into its own descendant
            if (isDescendant(prev, sourceKey, targetKey)) return prev;

            const [treeWithout, removed] = extractNode(prev, sourceKey);
            if (!removed) return prev;

            // Find the target's parent key
            let targetParentKey: string | null = null;
            const findParent = (nodes: TreeNode[], parentKey: string | null): boolean => {
                for (const n of nodes) {
                    if (n.temp_key === targetKey) {
                        targetParentKey = parentKey;
                        return true;
                    }
                    if (findParent(n.children, n.temp_key)) return true;
                }
                return false;
            };
            findParent(treeWithout, null);

            return insertNode(treeWithout, removed, targetKey, position, targetParentKey);
        });
    }, []);

    // ── Renumber sort_order ──
    const renumberTree = (nodes: TreeNode[]): TreeNode[] => {
        return nodes.map((n, i) => ({
            ...n,
            sort_order: i,
            children: renumberTree(n.children),
        }));
    };

    // ── Save ──
    const handleSave = async () => {
        if (!name.trim()) {
            toast.error('Name is required');
            return;
        }
        setSaving(true);
        try {
            const numberedTree = renumberTree(tree);
            const items = flattenTree(numberedTree);

            if (isNew) {
                await createRunbook.mutateAsync({ name, description, runbook_type: runbookType || undefined, items });
                toast.success('Runbook created!');
            } else {
                await updateRunbook.mutateAsync({ id: runbookId, name, description, runbook_type: runbookType || undefined, items });
                toast.success('Runbook updated!');
            }
            router.push('/templates?tab=runbooks');
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to save runbook'));
        } finally {
            setSaving(false);
        }
    };

    // ── Count total items ──
    const countItems = (nodes: TreeNode[]): number => {
        return nodes.reduce((sum, n) => sum + 1 + countItems(n.children), 0);
    };

    if (!isNew && rbLoading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    if (!isNew && !rbLoading && !allowedToEdit) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px] text-slate-400 text-center px-4">
                    {isSubmitted
                        ? "This runbook is locked while it's pending review. Withdraw the submission (or have a reviewer reject it) before editing."
                        : "You don't have permission to edit this runbook."}
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 max-w-7xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="icon" onClick={() => router.push('/templates?tab=runbooks')} className="text-slate-400 hover:text-white">
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-linear-to-br from-purple-500/20 to-pink-500/20">
                                    <GitBranch className="h-6 w-6 text-primary" />
                                </div>
                                {isNew ? 'New Runbook' : 'Edit Runbook'}
                            </h1>
                            <p className="text-slate-400 mt-1">
                                Build a hierarchical template tree for test cases
                            </p>
                        </div>
                    </div>
                    <Button
                        className="bg-primary hover:bg-primary/90 text-white gap-2"
                        onClick={handleSave}
                        disabled={saving}
                    >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        {isNew ? 'Create Runbook' : 'Save Changes'}
                    </Button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left: Runbook details + tree */}
                    <div className="lg:col-span-2 space-y-6">
                        {/* Name & Description */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardContent className="p-6 space-y-4">
                                <div>
                                    <Label className="text-slate-300">Name</Label>
                                    <Input
                                        value={name}
                                        onChange={e => setName(e.target.value)}
                                        placeholder="e.g. OWASP Web Application Pentest"
                                        className="mt-1.5 bg-slate-800/50 border-slate-700"
                                    />
                                </div>
                                <div>
                                    <Label className="text-slate-300">Type</Label>
                                    {/* Native <select> was rendering with native chrome
                                        (light background on some OSes) despite color-scheme:dark.
                                        Match the rest of the app by using the shadcn Select
                                        primitive. Empty-string is not a valid Radix Select value,
                                        so the "no type" state is represented by ``__none__`` and
                                        translated back when writing state. */}
                                    <Select
                                        value={runbookType || '__none__'}
                                        onValueChange={(v) => setRunbookType(v === '__none__' ? '' : v)}
                                    >
                                        <SelectTrigger className="mt-1.5 bg-slate-800/50 border-slate-700 text-white focus:ring-primary">
                                            <SelectValue placeholder="No type" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-700 text-white">
                                            <SelectItem value="__none__" className="text-slate-300">No type</SelectItem>
                                            {runbookTypes.map(t => (
                                                <SelectItem key={t.id} value={t.name} className="text-white">
                                                    {t.name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label className="text-slate-300">Description</Label>
                                    <Textarea
                                        value={description}
                                        onChange={e => setDescription(e.target.value)}
                                        placeholder="Describe what this runbook covers..."
                                        className="mt-1.5 bg-slate-800/50 border-slate-700 min-h-[80px]"
                                    />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Tree */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <CardTitle className="text-white text-base">
                                    Template Tree
                                    <Badge variant="secondary" className="ml-2 text-xs">{countItems(tree)} items</Badge>
                                </CardTitle>
                                <CardDescription>
                                    Drag nodes to reorder or nest them. Use the grip handle to drag.
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                {tree.length === 0 ? (
                                    <div className="text-center py-12 text-slate-500 border border-dashed border-slate-700 rounded-lg">
                                        <GitBranch className="h-10 w-10 mx-auto mb-3 opacity-20" />
                                        <p className="text-sm font-medium">No templates added yet</p>
                                        <p className="text-xs text-slate-600 mt-1">Add templates from the palette on the right</p>
                                    </div>
                                ) : (
                                    <div className="space-y-0.5">
                                        <TreeNodeList
                                            nodes={tree}
                                            depth={0}
                                            onRemove={removeNode}
                                            onIndent={indentNode}
                                            onOutdent={outdentNode}
                                            onToggleExpand={toggleExpand}
                                            draggedKey={draggedKey}
                                            dropTarget={dropTarget}
                                            onDragStart={setDraggedKey}
                                            onDragEnd={handleDragEnd}
                                            onDropTargetChange={handleDropTargetChange}
                                            onDrop={moveNode}
                                            parentKey={null}
                                        />
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Right: Template palette */}
                    <div className="space-y-4">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs sticky top-6">
                            <CardHeader className="pb-3">
                                <CardTitle className="text-white text-base">Template Palette</CardTitle>
                                <CardDescription>Click to add templates to the tree</CardDescription>
                                <div className="relative mt-2">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                    <Input
                                        placeholder="Search templates..."
                                        value={tmplSearch}
                                        onChange={e => setTmplSearch(e.target.value)}
                                        className="pl-9 bg-slate-800/50 border-slate-700"
                                    />
                                </div>
                            </CardHeader>
                            <CardContent className="max-h-[60vh] overflow-y-auto space-y-1">
                                {tmplLoading ? (
                                    <div className="flex items-center justify-center py-8">
                                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                                    </div>
                                ) : filteredTemplates.length === 0 ? (
                                    <p className="text-sm text-slate-500 text-center py-4">No templates found</p>
                                ) : (
                                    filteredTemplates.map(tmpl => {
                                        const isUsed = usedTemplateIds.has(tmpl.id);
                                        return (
                                            <button
                                                key={tmpl.id}
                                                onClick={() => !isUsed && addTemplateToTree(tmpl)}
                                                disabled={isUsed}
                                                className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all group ${isUsed
                                                    ? 'border-emerald-500/20 bg-emerald-500/5 opacity-60 cursor-not-allowed'
                                                    : 'border-slate-800 hover:border-primary/30 hover:bg-primary/5'
                                                    }`}
                                            >
                                                <div className="flex items-center justify-between">
                                                    <span className={`text-sm font-medium truncate mr-2 ${isUsed ? 'text-slate-400' : 'text-white'}`}>{tmpl.title}</span>
                                                    {isUsed ? (
                                                        <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                                                    ) : (
                                                        <Plus className="h-4 w-4 text-slate-600 group-hover:text-primary shrink-0 transition-colors" />
                                                    )}
                                                </div>
                                                <Badge variant="outline" className={`mt-1 text-[10px] ${isUsed ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'}`}>
                                                    {tmpl.category}
                                                </Badge>
                                            </button>
                                        );
                                    })
                                )}
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
}

// ─── Tree Node Renderer with Drag & Drop ─────────────────────────
function TreeNodeList({
    nodes,
    depth,
    onRemove,
    onIndent,
    onOutdent,
    onToggleExpand,
    draggedKey,
    dropTarget,
    onDragStart,
    onDragEnd,
    onDropTargetChange,
    onDrop,
    parentKey,
}: {
    nodes: TreeNode[];
    depth: number;
    onRemove: (key: string) => void;
    onIndent: (key: string) => void;
    onOutdent: (key: string) => void;
    onToggleExpand: (key: string) => void;
    draggedKey: string | null;
    dropTarget: { key: string; position: DropPosition } | null;
    onDragStart: (key: string) => void;
    onDragEnd: () => void;
    onDropTargetChange: (target: { key: string; position: DropPosition } | null) => void;
    onDrop: (sourceKey: string, targetKey: string, position: DropPosition) => void;
    parentKey: string | null;
}) {
    return (
        <>
            {nodes.map((node, index) => (
                <DraggableTreeNode
                    key={node.temp_key}
                    node={node}
                    index={index}
                    depth={depth}
                    onRemove={onRemove}
                    onIndent={onIndent}
                    onOutdent={onOutdent}
                    onToggleExpand={onToggleExpand}
                    draggedKey={draggedKey}
                    dropTarget={dropTarget}
                    onDragStart={onDragStart}
                    onDragEnd={onDragEnd}
                    onDropTargetChange={onDropTargetChange}
                    onDrop={onDrop}
                    parentKey={parentKey}
                />
            ))}
        </>
    );
}

function DraggableTreeNode({
    node,
    index,
    depth,
    onRemove,
    onIndent,
    onOutdent,
    onToggleExpand,
    draggedKey,
    dropTarget,
    onDragStart,
    onDragEnd,
    onDropTargetChange,
    onDrop,
    parentKey,
}: {
    node: TreeNode;
    index: number;
    depth: number;
    onRemove: (key: string) => void;
    onIndent: (key: string) => void;
    onOutdent: (key: string) => void;
    onToggleExpand: (key: string) => void;
    draggedKey: string | null;
    dropTarget: { key: string; position: DropPosition } | null;
    onDragStart: (key: string) => void;
    onDragEnd: () => void;
    onDropTargetChange: (target: { key: string; position: DropPosition } | null) => void;
    onDrop: (sourceKey: string, targetKey: string, position: DropPosition) => void;
    parentKey: string | null;
}) {
    const rowRef = useRef<HTMLDivElement>(null);
    const isDragging = draggedKey === node.temp_key;
    const isDropTarget = dropTarget?.key === node.temp_key;
    const dropPos = isDropTarget ? dropTarget.position : null;

    const handleDragStart = (e: React.DragEvent) => {
        e.dataTransfer.setData('text/plain', node.temp_key);
        e.dataTransfer.effectAllowed = 'move';
        // Slight delay so the ghost image captures the element
        requestAnimationFrame(() => onDragStart(node.temp_key));
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (draggedKey === node.temp_key) return;

        const rect = rowRef.current?.getBoundingClientRect();
        if (!rect) return;

        const y = e.clientY - rect.top;
        const h = rect.height;
        let position: DropPosition;

        if (y < h * 0.25) {
            position = 'before';
        } else if (y > h * 0.75) {
            position = 'after';
        } else {
            position = 'inside';
        }

        onDropTargetChange({ key: node.temp_key, position });
    };

    const handleDragLeave = (e: React.DragEvent) => {
        // Only clear if we've actually left this element entirely
        const related = e.relatedTarget as HTMLElement | null;
        if (rowRef.current && related && rowRef.current.contains(related)) return;
        if (dropTarget?.key === node.temp_key) {
            onDropTargetChange(null);
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        const sourceKey = e.dataTransfer.getData('text/plain');
        if (sourceKey && dropTarget) {
            onDrop(sourceKey, dropTarget.key, dropTarget.position);
        }
        onDragEnd();
    };

    // Drop indicator styles
    let dropIndicatorClass = '';
    if (isDropTarget && !isDragging) {
        if (dropPos === 'before') {
            dropIndicatorClass = 'before:absolute before:top-0 before:left-0 before:right-0 before:h-[2px] before:bg-primary before:rounded-full';
        } else if (dropPos === 'after') {
            dropIndicatorClass = 'after:absolute after:bottom-0 after:left-0 after:right-0 after:h-[2px] after:bg-primary after:rounded-full';
        } else {
            dropIndicatorClass = 'ring-2 ring-primary/60 ring-inset bg-primary/10';
        }
    }

    return (
        <div>
            <div
                ref={rowRef}
                draggable
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onDragEnd={onDragEnd}
                className={`relative flex items-center gap-2 py-2 px-3 rounded-lg border transition-all group ${isDragging
                    ? 'opacity-30 border-slate-800/30 bg-slate-800/10'
                    : 'border-slate-800/60 hover:border-slate-700 bg-slate-800/20 hover:bg-slate-800/40'
                    } ${dropIndicatorClass}`}
                style={{ marginLeft: `${depth * 28}px` }}
            >
                {/* Drag handle */}
                <div className="shrink-0 cursor-grab active:cursor-grabbing text-slate-600 hover:text-slate-400 transition-colors">
                    <GripVertical className="h-4 w-4" />
                </div>

                {/* Expand toggle */}
                <button
                    onClick={() => node.children.length > 0 && onToggleExpand(node.temp_key)}
                    className="shrink-0 w-5 h-5 flex items-center justify-center"
                >
                    {node.children.length > 0 ? (
                        node.expanded ? (
                            <ChevronDown className="h-4 w-4 text-slate-400" />
                        ) : (
                            <ChevronRight className="h-4 w-4 text-slate-400" />
                        )
                    ) : (
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                    )}
                </button>

                {/* Title */}
                <span className="text-sm text-white font-medium flex-1 truncate">
                    {node.template?.title || 'Unknown template'}
                </span>

                {/* Category badge */}
                <Badge variant="outline" className="text-[10px] bg-cyan-500/10 text-cyan-400 border-cyan-500/20 shrink-0">
                    {node.template?.category || '—'}
                </Badge>

                {/* Action buttons */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    {depth > 0 && (
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-white" onClick={() => onOutdent(node.temp_key)} title="Outdent">
                            <ArrowLeftIcon className="h-3.5 w-3.5" />
                        </Button>
                    )}
                    {index > 0 && (
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-white" onClick={() => onIndent(node.temp_key)} title="Indent (make child of above)">
                            <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                    )}
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-500 hover:text-red-400" onClick={() => onRemove(node.temp_key)} title="Remove">
                        <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                </div>
            </div>

            {/* Children */}
            {node.expanded && node.children.length > 0 && (
                <TreeNodeList
                    nodes={node.children}
                    depth={depth + 1}
                    onRemove={onRemove}
                    onIndent={onIndent}
                    onOutdent={onOutdent}
                    onToggleExpand={onToggleExpand}
                    draggedKey={draggedKey}
                    dropTarget={dropTarget}
                    onDragStart={onDragStart}
                    onDragEnd={onDragEnd}
                    onDropTargetChange={onDropTargetChange}
                    onDrop={onDrop}
                    parentKey={node.temp_key}
                />
            )}
        </div>
    );
}
