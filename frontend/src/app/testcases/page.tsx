/**
 * testcases/page.tsx — Test Cases List Page
 *
 * Hierarchical tree-table of all test cases across engagements, with
 * parent/child nesting and expand/collapse controls. Columns: title
 * (indented by depth), category (colour-coded badge), unresolved
 * discussions, execution status (Pending/Executed), and result
 * (Pass/Fail). Supports:
 *  - Full-text search with automatic tree expansion to show matches
 *  - Expand All / Collapse All with localStorage persistence
 *  - Per-row actions: view, add sub-test case, edit, delete
 *  - Real-time WebSocket updates for test case CRUD events
 *  - Deletion warns about children being promoted to root level
 */
'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
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
    Plus, Search, Eye, Edit, Trash2, CheckSquare, Loader2, MessageSquare,
    ChevronRight, ChevronDown, CornerDownRight
} from 'lucide-react';
import { useTestCases, useDeleteTestCase, buildTestCaseTree, flattenTree, TestCaseTreeNode } from '@/lib/hooks/use-testcases';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';

const categoryLabels: Record<string, string> = {
    RECONNAISSANCE: 'Reconnaissance',
    SCANNING: 'Scanning',
    EXPLOITATION: 'Exploitation',
    POST_EXPLOITATION: 'Post Exploitation',
    PRIVILEGE_ESCALATION: 'Privilege Escalation',
    PERSISTENCE: 'Persistence',
    LATERAL_MOVEMENT: 'Lateral Movement',
    WEB_APPLICATION: 'Web App',
    SOCIAL_ENGINEERING: 'Social Engineering',
    PHYSICAL: 'Physical',
    OTHER: 'Other',
};

const categoryColors: Record<string, string> = {
    RECONNAISSANCE: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    SCANNING: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    EXPLOITATION: 'bg-red-500/10 text-red-400 border-red-500/20',
    POST_EXPLOITATION: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
    PRIVILEGE_ESCALATION: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    WEB_APPLICATION: 'bg-green-500/10 text-green-400 border-green-500/20',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

export default function TestCasesPage() {
    const router = useRouter();
    const { user } = useAuthStore();
    const [searchTerm, setSearchTerm] = useState('');
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
    const tcInitialized = useRef(false);

    const { data: testcases = [], isLoading, error, refetch } = useTestCases();
    const deleteTestCase = useDeleteTestCase();
    const { confirm, ConfirmDialog } = useConfirmDialog();
    const queryClient = useQueryClient();

    // ── Live updates via WebSocket ───────────────────────────────
    useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') {
                const rt = (data.resource_type || '').toLowerCase();
                if (rt === 'testcase') {
                    queryClient.invalidateQueries({ queryKey: ['testcases'] });
                }
            }
        },
    });

    // Build tree from flat list
    const tree = useMemo(() => buildTestCaseTree(testcases), [testcases]);

    // Load saved state from localStorage on mount, or auto-expand if no saved state
    useEffect(() => {
        if (tcInitialized.current || testcases.length === 0) return;
        tcInitialized.current = true;

        const saved = localStorage.getItem('redwire_tc_expanded');
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed)) {
                    setExpandedIds(new Set(parsed));
                    return;
                }
            } catch { /* ignore */ }
        }
        // No saved state — auto-expand all parents
        const allParentIds = new Set(
            testcases
                .filter(tc => testcases.some(child => child.parent_id === tc.id))
                .map(tc => tc.id)
        );
        setExpandedIds(allParentIds);
    }, [testcases]);

    // Persist expanded state (only after initialization)
    useEffect(() => {
        if (!tcInitialized.current) return;
        localStorage.setItem('redwire_tc_expanded', JSON.stringify([...expandedIds]));
    }, [expandedIds]);

    // Filter tree (show matching nodes + ancestors)
    const filteredTree = useMemo(() => {
        if (!searchTerm) return tree;

        const term = searchTerm.toLowerCase();

        function matchesSearch(node: TestCaseTreeNode): boolean {
            return node.title.toLowerCase().includes(term) ||
                node.description.toLowerCase().includes(term) ||
                node.category.toLowerCase().includes(term);
        }

        function filterNodes(nodes: TestCaseTreeNode[]): TestCaseTreeNode[] {
            const result: TestCaseTreeNode[] = [];
            for (const node of nodes) {
                const filteredChildren = filterNodes(node.children);
                if (matchesSearch(node) || filteredChildren.length > 0) {
                    result.push({
                        ...node,
                        children: filteredChildren,
                    });
                }
            }
            return result;
        }

        return filterNodes(tree);
    }, [tree, searchTerm]);

    // Flatten for rendering
    const displayRows = useMemo(() => {
        return flattenTree(filteredTree, searchTerm ? new Set(testcases.map(tc => tc.id)) : expandedIds);
    }, [filteredTree, expandedIds, searchTerm, testcases]);

    const toggleExpand = (id: string) => {
        setExpandedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const expandAll = () => {
        const allParentIds = new Set(
            testcases
                .filter(tc => testcases.some(child => child.parent_id === tc.id))
                .map(tc => tc.id)
        );
        setExpandedIds(allParentIds);
    };

    const collapseAll = () => {
        setExpandedIds(new Set());
    };

    const handleDelete = async (id: string) => {
        const hasChildren = testcases.some(tc => tc.parent_id === id);
        if (hasChildren) {
            const childCount = testcases.filter(tc => tc.parent_id === id).length;
            const result = await confirm({
                title: 'Delete Test Case with Children',
                description: `This test case has ${childCount} direct sub-test case${childCount !== 1 ? 's' : ''}. What would you like to do?`,
                confirmLabel: 'Delete All (with children)',
                variant: 'destructive',
                extraAction: {
                    label: 'Delete Only This',
                    variant: 'outline' as const,
                },
            });
            if (result === false) return;
            const cascade = result === true;
            try {
                await deleteTestCase.mutateAsync({ id, cascade });
                toast.success(cascade ? 'Test case and all children deleted' : 'Test case deleted (children moved to root)');
                refetch();
            } catch (error: any) {
                toast.error(getErrorMessage(error, 'Failed to delete test case'));
            }
        } else {
            const confirmed = await confirm({
                title: 'Delete Test Case',
                description: 'Are you sure you want to delete this test case?',
            });
            if (!confirmed) return;
            try {
                await deleteTestCase.mutateAsync({ id });
                refetch();
            } catch (error: any) {
                toast.error(getErrorMessage(error, 'Failed to delete test case'));
            }
        }
    };

    const isAdmin = user?.role === 'admin' || user?.role === 'read_only_admin' || user?.role === 'team_lead';

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                            <CheckSquare className="h-8 w-8 text-primary" />
                            Test Cases
                        </h1>
                        <p className="text-slate-400 mt-1">Track security testing checklists and results</p>
                    </div>
                    <Button onClick={() => router.push('/testcases/new')} className="bg-primary hover:bg-primary/90 text-white shadow-lg shadow-primary/20">
                        <Plus className="h-4 w-4 mr-2" />
                        New Test Case
                    </Button>
                </div>

                {/* Search & Tree Controls */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                    <CardContent className="pt-6">
                        <div className="flex gap-3">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                                <Input
                                    placeholder="Search test cases..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="pl-10 bg-slate-800/50 border-slate-700 text-white focus:ring-primary focus:border-primary"
                                />
                            </div>
                            <Button variant="outline" size="sm" onClick={expandAll} className="text-slate-300 border-slate-700 hover:bg-slate-800">
                                Expand All
                            </Button>
                            <Button variant="outline" size="sm" onClick={collapseAll} className="text-slate-300 border-slate-700 hover:bg-slate-800">
                                Collapse All
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Test Cases Tree Table */}
                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs shadow-xl overflow-hidden">
                    <CardHeader>
                        <CardTitle className="text-white">
                            All Test Cases {!isLoading && `(${testcases.length})`}
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="px-0 pt-0">
                        {isLoading ? (
                            <div className="flex items-center justify-center py-10">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        ) : error ? (
                            <div className="text-center py-10 text-red-400">
                                Failed to load test cases.
                            </div>
                        ) : (
                            <div className="border-t border-slate-800">
                                <Table>
                                    <TableHeader className="bg-slate-800/30">
                                        <TableRow className="border-slate-800 hover:bg-transparent">
                                            <TableHead className="text-slate-300 font-semibold pl-6">
                                                Title
                                            </TableHead>
                                            <TableHead className="text-slate-300 font-semibold">
                                                Category
                                            </TableHead>
                                            <TableHead className="text-slate-300 font-semibold">Discussions</TableHead>
                                            <TableHead className="text-slate-300 font-semibold">
                                                Status
                                            </TableHead>
                                            <TableHead className="text-slate-300 font-semibold">Result</TableHead>
                                            <TableHead className="text-right text-slate-300 font-semibold pr-6">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {displayRows.length === 0 ? (
                                            <TableRow>
                                                <TableCell colSpan={6} className="text-center text-slate-400 py-10">
                                                    No test cases found.
                                                </TableCell>
                                            </TableRow>
                                        ) : (
                                            displayRows.map((tc) => {
                                                const hasChildren = tc.children.length > 0;
                                                const isExpanded = expandedIds.has(tc.id);
                                                const depthPadding = 24 + tc.depth * 28; // base 24px + 28px per level

                                                return (
                                                    <TableRow
                                                        key={tc.id}
                                                        className="border-slate-800 hover:bg-slate-800/50 group"
                                                    >
                                                        <TableCell
                                                            className="font-medium text-white max-w-xs"
                                                            style={{ paddingLeft: `${depthPadding}px` }}
                                                        >
                                                            <div className="flex items-center gap-2">
                                                                {hasChildren ? (
                                                                    <button
                                                                        onClick={() => toggleExpand(tc.id)}
                                                                        className="p-0.5 rounded hover:bg-slate-700/50 transition-colors shrink-0"
                                                                    >
                                                                        {isExpanded ? (
                                                                            <ChevronDown className="h-4 w-4 text-slate-400" />
                                                                        ) : (
                                                                            <ChevronRight className="h-4 w-4 text-slate-400" />
                                                                        )}
                                                                    </button>
                                                                ) : (
                                                                    <span className="w-5 shrink-0">
                                                                        {tc.depth > 0 && (
                                                                            <CornerDownRight className="h-3.5 w-3.5 text-slate-600" />
                                                                        )}
                                                                    </span>
                                                                )}
                                                                <span className="truncate">{tc.title}</span>
                                                            </div>
                                                        </TableCell>
                                                        <TableCell>
                                                            <Badge className={categoryColors[tc.category] || categoryColors.OTHER}>
                                                                {categoryLabels[tc.category] || tc.category}
                                                            </Badge>
                                                        </TableCell>
                                                        <TableCell>
                                                            {tc.unresolved_thread_count && tc.unresolved_thread_count > 0 ? (
                                                                <div className="flex items-center gap-2 text-amber-400">
                                                                    <MessageSquare className="h-4 w-4" />
                                                                    <span className="text-sm font-medium">{tc.unresolved_thread_count}</span>
                                                                </div>
                                                            ) : (
                                                                <span className="text-slate-600 text-sm">—</span>
                                                            )}
                                                        </TableCell>
                                                        <TableCell>
                                                            {tc.is_executed ? (
                                                                <Badge className="bg-green-500/10 text-green-400 border-green-500/20">Executed</Badge>
                                                            ) : (
                                                                <Badge variant="outline" className="text-slate-400">Pending</Badge>
                                                            )}
                                                        </TableCell>
                                                        <TableCell>
                                                            {tc.is_executed ? (
                                                                tc.is_successful ? (
                                                                    <Badge className="bg-green-500/10 text-green-400 border-green-500/20">Pass</Badge>
                                                                ) : (
                                                                    <Badge className="bg-red-500/10 text-red-400 border-red-500/20">Fail</Badge>
                                                                )
                                                            ) : '—'}
                                                        </TableCell>
                                                        <TableCell className="text-right pr-6">
                                                            <div className="flex justify-end gap-1">
                                                                <Button
                                                                    variant="ghost" size="icon"
                                                                    onClick={() => router.push(`/testcases/${tc.id}`)}
                                                                    className="text-slate-400 hover:text-white"
                                                                    title="View"
                                                                >
                                                                    <Eye className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="ghost" size="icon"
                                                                    onClick={() => router.push(`/testcases/new?parentId=${tc.id}&engagementId=${tc.engagement_id}`)}
                                                                    className="text-slate-400 hover:text-primary"
                                                                    title="Add Sub-Test Case"
                                                                >
                                                                    <Plus className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="ghost" size="icon"
                                                                    onClick={() => router.push(`/testcases/${tc.id}/edit`)}
                                                                    className="text-slate-400 hover:text-white"
                                                                    title="Edit"
                                                                >
                                                                    <Edit className="h-4 w-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="ghost" size="icon"
                                                                    onClick={() => handleDelete(tc.id)}
                                                                    disabled={deleteTestCase.isPending}
                                                                    className="text-slate-400 hover:text-red-400"
                                                                    title="Delete"
                                                                >
                                                                    <Trash2 className="h-4 w-4" />
                                                                </Button>
                                                            </div>
                                                        </TableCell>
                                                    </TableRow>
                                                );
                                            })
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
