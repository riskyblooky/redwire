'use client';

import { useState, useMemo } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Search, FolderTree, Loader2, ChevronRight, ChevronDown, CornerDownRight, Home, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface MoveTestCaseItem {
    id: string;
    title: string;
    parent_id: string | null;
    category: string;
}

export interface MoveTreeNode extends MoveTestCaseItem {
    children: MoveTreeNode[];
    depth: number;
}

interface MoveTestCaseDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    testcases: MoveTestCaseItem[];
    movingTestCase: { id: string; title: string; parent_id: string | null } | null;
    isMoving?: boolean;
    onMove: (testcaseId: string, newParentId: string | null) => void;
}

function buildTree(items: MoveTestCaseItem[]): MoveTreeNode[] {
    const map = new Map<string, MoveTreeNode>();
    const roots: MoveTreeNode[] = [];

    for (const item of items) {
        map.set(item.id, { ...item, children: [], depth: 0 });
    }

    for (const item of items) {
        const node = map.get(item.id)!;
        if (item.parent_id && map.has(item.parent_id)) {
            map.get(item.parent_id)!.children.push(node);
        } else {
            roots.push(node);
        }
    }

    function setDepths(nodes: MoveTreeNode[], depth: number) {
        for (const n of nodes) {
            n.depth = depth;
            setDepths(n.children, depth + 1);
        }
    }
    setDepths(roots, 0);
    return roots;
}

/** Collect all descendant IDs of a node (including itself) */
function getDescendantIds(items: MoveTestCaseItem[], rootId: string): Set<string> {
    const ids = new Set<string>([rootId]);
    let added = true;
    while (added) {
        added = false;
        for (const item of items) {
            if (item.parent_id && ids.has(item.parent_id) && !ids.has(item.id)) {
                ids.add(item.id);
                added = true;
            }
        }
    }
    return ids;
}

export function MoveTestCaseDialog({
    open,
    onOpenChange,
    testcases,
    movingTestCase,
    isMoving = false,
    onMove,
}: MoveTestCaseDialogProps) {
    const [search, setSearch] = useState('');
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

    // IDs to disable (the moving test case + all its descendants)
    const disabledIds = useMemo(() => {
        if (!movingTestCase) return new Set<string>();
        return getDescendantIds(testcases, movingTestCase.id);
    }, [testcases, movingTestCase]);

    // Build tree from all items (excluding disabled from search but still showing them disabled)
    const tree = useMemo(() => buildTree(testcases), [testcases]);

    // Filter logic: if search is active, show only matching items in a flat list
    const filteredFlat = useMemo(() => {
        if (!search.trim()) return null;
        const q = search.toLowerCase();
        return testcases.filter(
            (t) => t.title.toLowerCase().includes(q) && !disabledIds.has(t.id)
        );
    }, [testcases, search, disabledIds]);

    const handleOpenChange = (isOpen: boolean) => {
        if (!isOpen) {
            setSearch('');
        }
        onOpenChange(isOpen);
    };

    const handleMove = (newParentId: string | null) => {
        if (!movingTestCase) return;
        // Don't move if already at this parent
        if (movingTestCase.parent_id === newParentId) return;
        onMove(movingTestCase.id, newParentId);
    };

    const toggleExpand = (id: string) => {
        setExpandedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    // Auto-expand all when dialog opens
    useMemo(() => {
        if (open) {
            const allIds = new Set(testcases.filter(t => testcases.some(c => c.parent_id === t.id)).map(t => t.id));
            setExpandedIds(allIds);
        }
    }, [open, testcases]);

    const isCurrentParent = (id: string | null) => {
        return movingTestCase?.parent_id === id || (movingTestCase?.parent_id === null && id === null);
    };

    const renderNode = (node: MoveTreeNode): React.ReactNode => {
        const isDisabled = disabledIds.has(node.id);
        const isCurrent = isCurrentParent(node.id);
        const hasChildren = node.children.length > 0;
        const isExpanded = expandedIds.has(node.id);
        const indent = node.depth * 20;

        return (
            <div key={node.id}>
                <button
                    onClick={() => {
                        if (isDisabled || isCurrent) return;
                        if (hasChildren) toggleExpand(node.id);
                        handleMove(node.id);
                    }}
                    disabled={isDisabled || isMoving}
                    className={cn(
                        "w-full text-left px-3 py-2 flex items-center gap-2 rounded-md transition-all duration-100",
                        isDisabled
                            ? "opacity-30 cursor-not-allowed"
                            : isCurrent
                                ? "bg-indigo-500/10 border border-indigo-500/30 cursor-default"
                                : "hover:bg-slate-800 cursor-pointer",
                    )}
                    style={{ paddingLeft: `${12 + indent}px` }}
                >
                    {hasChildren ? (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                toggleExpand(node.id);
                            }}
                            className="p-0.5 rounded hover:bg-slate-700/50 shrink-0"
                        >
                            {isExpanded ? (
                                <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
                            ) : (
                                <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
                            )}
                        </button>
                    ) : (
                        <span className="w-[18px] shrink-0 flex justify-center">
                            {node.depth > 0 && <CornerDownRight className="h-3 w-3 text-slate-600" />}
                        </span>
                    )}
                    <span className={cn(
                        "text-sm truncate flex-1",
                        isDisabled ? "text-slate-600" : isCurrent ? "text-indigo-300 font-medium" : "text-slate-300"
                    )}>
                        {node.title}
                    </span>
                    {isCurrent && (
                        <Badge className="text-[9px] h-4 px-1.5 bg-indigo-500/20 text-indigo-400 border-indigo-500/30 shrink-0">
                            Current Parent
                        </Badge>
                    )}
                    {isDisabled && node.id === movingTestCase?.id && (
                        <Badge className="text-[9px] h-4 px-1.5 bg-amber-500/20 text-amber-400 border-amber-500/30 shrink-0">
                            Moving
                        </Badge>
                    )}
                </button>
                {hasChildren && isExpanded && (
                    <div>
                        {node.children.map(child => renderNode(child))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[500px] p-0 gap-0 overflow-hidden max-h-[80vh] flex flex-col">
                <div className="p-6 pb-4 space-y-4 shrink-0">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            <FolderTree className="h-5 w-5 text-indigo-400" />
                            Move Test Case
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            {movingTestCase ? (
                                <>Select a new parent for <span className="text-white font-medium">&ldquo;{movingTestCase.title}&rdquo;</span></>
                            ) : 'Select a test case to move'}
                        </DialogDescription>
                    </DialogHeader>

                    {/* Search */}
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                        <Input
                            placeholder="Search test cases..."
                            className="pl-10 h-9 bg-slate-950/50 border-slate-800 text-white rounded-lg focus:ring-primary/30 placeholder:text-slate-600"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            autoFocus
                        />
                    </div>
                </div>

                {/* Tree / List */}
                <div className="flex-1 overflow-y-auto min-h-0 px-4 pb-4">
                    {/* Root Level option */}
                    <button
                        onClick={() => handleMove(null)}
                        disabled={isMoving || isCurrentParent(null)}
                        className={cn(
                            "w-full text-left px-3 py-2.5 flex items-center gap-2.5 rounded-md transition-all duration-100 mb-2",
                            isCurrentParent(null)
                                ? "bg-indigo-500/10 border border-indigo-500/30 cursor-default"
                                : "hover:bg-slate-800 cursor-pointer border border-transparent"
                        )}
                    >
                        <Home className="h-4 w-4 text-slate-400 shrink-0" />
                        <span className={cn(
                            "text-sm font-medium",
                            isCurrentParent(null) ? "text-indigo-300" : "text-slate-300"
                        )}>
                            Root Level
                        </span>
                        {isCurrentParent(null) && (
                            <Badge className="text-[9px] h-4 px-1.5 bg-indigo-500/20 text-indigo-400 border-indigo-500/30 shrink-0 ml-auto">
                                Current
                            </Badge>
                        )}
                    </button>

                    <div className="h-px bg-slate-800/60 mb-2" />

                    {isMoving ? (
                        <div className="flex flex-col items-center justify-center py-12">
                            <Loader2 className="h-5 w-5 animate-spin text-indigo-400 mb-2" />
                            <p className="text-slate-500 text-sm">Moving test case...</p>
                        </div>
                    ) : filteredFlat ? (
                        // Search results — flat list
                        filteredFlat.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12">
                                <p className="text-slate-500 text-sm">No matching test cases</p>
                            </div>
                        ) : (
                            <div className="space-y-0.5">
                                {filteredFlat.map(t => (
                                    <button
                                        key={t.id}
                                        onClick={() => handleMove(t.id)}
                                        disabled={isCurrentParent(t.id)}
                                        className={cn(
                                            "w-full text-left px-3 py-2 flex items-center gap-2 rounded-md transition-all duration-100",
                                            isCurrentParent(t.id)
                                                ? "bg-indigo-500/10 border border-indigo-500/30 cursor-default"
                                                : "hover:bg-slate-800 cursor-pointer"
                                        )}
                                    >
                                        <span className="text-sm text-slate-300 truncate flex-1">{t.title}</span>
                                        <Badge variant="outline" className="text-[9px] px-1.5 h-4 border-slate-700 text-slate-500 shrink-0">
                                            {t.category.replace(/_/g, ' ')}
                                        </Badge>
                                        {isCurrentParent(t.id) && (
                                            <Check className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                                        )}
                                    </button>
                                ))}
                            </div>
                        )
                    ) : (
                        // Tree view
                        <div className="space-y-0.5">
                            {tree.map(node => renderNode(node))}
                        </div>
                    )}
                </div>

                {/* Footer hint */}
                <div className="px-6 py-2.5 border-t border-slate-800/60 shrink-0">
                    <p className="text-[10px] text-slate-600 text-center">
                        Click a test case to move under it, or select &ldquo;Root Level&rdquo; to un-nest
                    </p>
                </div>
            </DialogContent>
        </Dialog>
    );
}
