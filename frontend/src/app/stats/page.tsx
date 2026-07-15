/**
 * stats/page.tsx — Operations Analytics
 *
 * A tabbed, GLOBAL analytics surface. The first tab ("Analytics") is the
 * built-in rich Recharts view (AnalyticsOverview) — pinned and always
 * present. Additional tabs are admin/curator-defined widget pages (the same
 * widget system as the dashboard), whose layout is shared by everyone.
 * Managing pages/tabs is gated on the MANAGE_STATS_PAGES permission; the
 * data inside widgets honors the platform Stats Scope Mode.
 */
'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog';
import { BarChart3, Plus, Loader2, LayoutDashboard } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { RedWireSpinner } from '@/components/ui/redwire-spinner';
import { useGlobalPermission } from '@/lib/hooks/use-permissions';
import { useDashboardWidgets } from '@/lib/hooks/use-dashboard-widgets';
import {
    useStatsPages, useCreateStatsPage, useUpdateStatsPage, useDeleteStatsPage,
    type StatsPage,
} from '@/lib/hooks/use-stats-pages';
import AnalyticsOverview from '@/components/stats/analytics-overview';
import StatsPageView from '@/components/stats/stats-page-view';

const ANALYTICS_TAB = 'analytics';

export default function StatsPage() {
    const router = useRouter();
    const { isAuthenticated, isLoading: authLoading } = useAuthStore();
    const canManage = useGlobalPermission('manage_stats_pages');

    const { data: pages = [], isLoading: pagesLoading } = useStatsPages();
    const { data: widgets = [], isLoading: widgetsLoading } = useDashboardWidgets();
    const createPage = useCreateStatsPage();
    const updatePage = useUpdateStatsPage();
    const deletePage = useDeleteStatsPage();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const [activeId, setActiveId] = useState<string>(ANALYTICS_TAB);

    // Create/rename dialog state
    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogMode, setDialogMode] = useState<'create' | 'rename'>('create');
    const [dialogName, setDialogName] = useState('');
    const [renameTarget, setRenameTarget] = useState<StatsPage | null>(null);

    useEffect(() => {
        if (!authLoading && !isAuthenticated) router.push('/login');
    }, [isAuthenticated, authLoading, router]);

    // If the active tab points at a page that no longer exists, fall back.
    useEffect(() => {
        if (activeId === ANALYTICS_TAB) return;
        if (!pagesLoading && !pages.some(p => p.id === activeId)) {
            setActiveId(ANALYTICS_TAB);
        }
    }, [activeId, pages, pagesLoading]);

    const activePage = useMemo(
        () => pages.find(p => p.id === activeId) || null,
        [pages, activeId],
    );

    const openCreate = () => {
        setDialogMode('create');
        setDialogName('');
        setRenameTarget(null);
        setDialogOpen(true);
    };

    const openRename = (page: StatsPage) => {
        setDialogMode('rename');
        setDialogName(page.name);
        setRenameTarget(page);
        setDialogOpen(true);
    };

    const submitDialog = async () => {
        const name = dialogName.trim();
        if (!name) return;
        try {
            if (dialogMode === 'create') {
                const created = await createPage.mutateAsync({ name });
                setActiveId(created.id);
                toast.success(`Created "${name}"`);
            } else if (renameTarget) {
                await updatePage.mutateAsync({ id: renameTarget.id, name });
                toast.success('Renamed');
            }
            setDialogOpen(false);
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Something went wrong'));
        }
    };

    const handleDelete = async (page: StatsPage) => {
        const ok = await confirm({
            title: 'Delete stats page',
            description: `Delete "${page.name}"? This is a shared page — it will be removed for everyone.`,
            confirmLabel: 'Delete page',
            variant: 'destructive',
        });
        if (!ok) return;
        try {
            await deletePage.mutateAsync(page.id);
            if (activeId === page.id) setActiveId(ANALYTICS_TAB);
            toast.success(`Deleted "${page.name}"`);
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to delete page'));
        }
    };

    if (authLoading || pagesLoading || widgetsLoading) {
        return <RedWireSpinner message="Loading analytics" />;
    }
    if (!isAuthenticated) return null;

    const dialogBusy = createPage.isPending || updatePage.isPending;

    return (
        <DashboardLayout>
            <div className="p-6 space-y-5">
                {/* Header */}
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 rounded-lg">
                        <BarChart3 className="h-6 w-6 text-indigo-400" />
                    </div>
                    <h1 className="text-3xl font-bold text-white tracking-tight">Operations Analytics</h1>
                </div>

                {/* Top-level tab bar */}
                <div className="flex items-center gap-2 border-b border-slate-800 pb-2 flex-wrap">
                    <TabButton
                        active={activeId === ANALYTICS_TAB}
                        onClick={() => setActiveId(ANALYTICS_TAB)}
                        icon={<BarChart3 className="h-3.5 w-3.5" />}
                        label="Analytics"
                    />
                    {pages.map(page => (
                        <TabButton
                            key={page.id}
                            active={activeId === page.id}
                            onClick={() => setActiveId(page.id)}
                            icon={<LayoutDashboard className="h-3.5 w-3.5" />}
                            label={page.name}
                        />
                    ))}
                    {canManage && (
                        <Button
                            size="sm" variant="ghost" onClick={openCreate}
                            className="h-8 text-xs text-slate-400 hover:text-primary gap-1.5"
                        >
                            <Plus className="h-3.5 w-3.5" /> New Page
                        </Button>
                    )}
                </div>

                {/* Active tab content */}
                {activeId === ANALYTICS_TAB ? (
                    <AnalyticsOverview />
                ) : activePage ? (
                    <StatsPageView
                        page={activePage}
                        widgets={widgets}
                        canManage={canManage}
                        onRename={() => openRename(activePage)}
                        onDelete={() => handleDelete(activePage)}
                    />
                ) : null}
            </div>

            <ConfirmDialog />

            {/* Create / rename dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[420px]">
                    <DialogHeader>
                        <DialogTitle>{dialogMode === 'create' ? 'New Stats Page' : 'Rename Page'}</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            {dialogMode === 'create'
                                ? 'Add a new shared tab. Everyone sees the same page and widgets.'
                                : 'Rename this shared stats page.'}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2 py-2">
                        <Label className="text-xs text-slate-400">Page name</Label>
                        <Input
                            value={dialogName}
                            onChange={(e) => setDialogName(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') submitDialog(); }}
                            placeholder="e.g. Executive Summary"
                            autoFocus
                            className="bg-slate-950 border-slate-700 text-white"
                        />
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setDialogOpen(false)} disabled={dialogBusy}>Cancel</Button>
                        <Button onClick={submitDialog} disabled={!dialogName.trim() || dialogBusy}
                            className="bg-primary hover:bg-primary/90 text-primary-foreground">
                            {dialogBusy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                            {dialogMode === 'create' ? 'Create' : 'Save'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </DashboardLayout>
    );
}

function TabButton({ active, onClick, icon, label }: {
    active: boolean; onClick: () => void; icon: React.ReactNode; label: string;
}) {
    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                active
                    ? 'bg-primary/15 text-primary'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
        >
            {icon}
            <span className="max-w-[160px] truncate">{label}</span>
        </button>
    );
}
