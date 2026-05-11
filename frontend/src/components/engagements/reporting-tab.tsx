'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    DragEndEvent,
} from '@dnd-kit/core';
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
    DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
    FileText, Download, Loader2, AlertTriangle, CheckCircle, Info,
    Plus, GripVertical, Trash2, Save, Import, Upload, Search,
    BookOpen, ClipboardList, Type, ChevronDown, LayoutTemplate, Palette, Sparkles, Package, Network,
    Eye, Paperclip, ExternalLink, X, Archive
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useGenerateReport, useSaveReportToEngagement, downloadBlob, type GenerateReportResult } from '@/lib/hooks/use-reports';
import { usePermission } from '@/lib/hooks/use-permissions';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import {
    useReportLayouts,
    useCreateReportLayout,
    useUpdateReportLayout,
    useDeleteReportLayout,
    useImportLayoutFromTemplate,
} from '@/lib/hooks/use-report-layouts';
import { useReportLayoutTemplates, useCreateReportLayoutTemplate } from '@/lib/hooks/use-report-layout-templates';
import { useReportThemes } from '@/lib/hooks/use-report-themes';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';
import { SectionType } from '@/lib/types';
import { toast } from 'sonner';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useCleanupArtifacts } from '@/lib/hooks/use-cleanup-artifacts';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import dynamic from 'next/dynamic';

const TiptapEditor = dynamic(() => import('@/components/ui/tiptap-editor'), { ssr: false });
const AttackGraph = dynamic(
    () => import('@/components/engagements/attack-graph').then(m => ({ default: m.AttackGraph })),
    { ssr: false, loading: () => <div className="h-[300px] flex items-center justify-center text-slate-500"><Loader2 className="h-6 w-6 animate-spin" /></div> }
);

// ── Local section type for in-memory editing ──
interface LocalSection {
    localId: string; // for dnd-kit key; may not map to a real id
    section_type: SectionType;
    title: string;
    content: string;
}

function newLocalId() {
    return 'local_' + Math.random().toString(36).slice(2, 10);
}

// ── Sortable Section Card ──
function SortableSectionCard({
    section,
    isSelected,
    onClick,
    onDelete,
}: {
    section: LocalSection;
    isSelected: boolean;
    onClick: () => void;
    onDelete: () => void;
}) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: section.localId });
    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
    };

    const typeLabel = section.section_type === SectionType.TEXT ? 'Text' : section.section_type === SectionType.FINDINGS ? 'Findings' : section.section_type === SectionType.TESTCASES ? 'Test Cases' : 'Cleanup';
    const typeColor = section.section_type === SectionType.TEXT
        ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
        : section.section_type === SectionType.FINDINGS
            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
            : section.section_type === SectionType.TESTCASES
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : 'bg-lime-500/10 text-lime-400 border-lime-500/20';
    const typeIcon = section.section_type === SectionType.TEXT
        ? <Type className="h-3.5 w-3.5" />
        : section.section_type === SectionType.FINDINGS
            ? <Search className="h-3.5 w-3.5" />
            : section.section_type === SectionType.TESTCASES
                ? <ClipboardList className="h-3.5 w-3.5" />
                : <Sparkles className="h-3.5 w-3.5" />;

    return (
        <div
            ref={setNodeRef}
            style={style}
            className={cn(
                'flex items-center gap-2 p-3 rounded-lg border transition-all cursor-pointer group',
                isSelected
                    ? 'border-indigo-500/50 bg-indigo-500/10 shadow-lg shadow-indigo-500/5'
                    : 'border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-800/40',
            )}
            onClick={onClick}
        >
            <button
                {...attributes}
                {...listeners}
                className="p-1 rounded hover:bg-slate-700/50 cursor-grab active:cursor-grabbing text-slate-500 hover:text-slate-300 touch-none"
                onClick={e => e.stopPropagation()}
            >
                <GripVertical className="h-4 w-4" />
            </button>
            <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{section.title || 'Untitled Section'}</p>
            </div>
            <Badge variant="outline" className={cn('text-[10px] gap-1 shrink-0', typeColor)}>
                {typeIcon} {typeLabel}
            </Badge>
            <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                onClick={e => { e.stopPropagation(); onDelete(); }}
            >
                <Trash2 className="h-3.5 w-3.5" />
            </Button>
        </div>
    );
}


// ═══════════════════════════════════════════════════════════════════
// Main Reporting Tab
// ═══════════════════════════════════════════════════════════════════
interface ReportingTabProps {
    engagementId: string;
    engagementName: string;
}

export function ReportingTab({ engagementId, engagementName }: ReportingTabProps) {
    // ── Permissions & collaboration ──
    const canGenerateReport = usePermission(engagementId, 'report_generate');
    const { activeUsers } = useCollaboration({ resourceType: 'report', resourceId: engagementId });

    // ── Report generation ──
    const [format, setFormat] = useState<'pdf' | 'markdown' | 'json_zip'>('pdf');
    const [isGenerating, setIsGenerating] = useState(false);
    const [lastGenerated, setLastGenerated] = useState<string | null>(null);
    const [includeEvidence, setIncludeEvidence] = useState(true);
    const generateReport = useGenerateReport();
    const saveToEngagement = useSaveReportToEngagement();

    // ── Report preview state ──
    const [previewOpen, setPreviewOpen] = useState(false);
    const [previewResult, setPreviewResult] = useState<GenerateReportResult | null>(null);
    const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    // ── Report layouts CRUD ──
    const { data: layouts = [], isLoading: layoutsLoading } = useReportLayouts(engagementId);
    const createLayout = useCreateReportLayout();
    const updateLayout = useUpdateReportLayout();
    const deleteLayout = useDeleteReportLayout();
    const importFromTemplate = useImportLayoutFromTemplate();

    // ── Templates ──
    const { data: templates = [] } = useReportLayoutTemplates();
    const saveAsTemplate = useCreateReportLayoutTemplate();

    // ── Report Themes ──
    const { data: themes = [] } = useReportThemes();
    const [selectedThemeId, setSelectedThemeId] = useState<string | null>(null);

    // Auto-select default theme
    useEffect(() => {
        if (themes.length > 0 && !selectedThemeId) {
            const defaultTheme = themes.find(t => t.is_default);
            if (defaultTheme) setSelectedThemeId(defaultTheme.id);
        }
    }, [themes, selectedThemeId]);

    // ── Local state ──
    const [selectedLayoutId, setSelectedLayoutId] = useState<string | null>(null);
    const [layoutName, setLayoutName] = useState('');
    const [sections, setSections] = useState<LocalSection[]>([]);
    const [selectedSectionIdx, setSelectedSectionIdx] = useState<number | null>(null);
    const [isDirty, setIsDirty] = useState(false);

    // ── Temporary item selection (not saved in layout) ──
    const { data: allFindings = [] } = useFindings({ engagement_id: engagementId });
    const { data: allTestCases = [] } = useTestCases(engagementId);
    const { data: allCleanup = [] } = useCleanupArtifacts(engagementId);
    const [selectedFindingIds, setSelectedFindingIds] = useState<Set<string> | null>(null); // null = all
    const [selectedTestcaseIds, setSelectedTestcaseIds] = useState<Set<string> | null>(null);
    const [selectedCleanupIds, setSelectedCleanupIds] = useState<Set<string> | null>(null);

    // ── Dialogs ──
    const [importDialogOpen, setImportDialogOpen] = useState(false);
    const [saveTemplateDialogOpen, setSaveTemplateDialogOpen] = useState(false);
    const [newLayoutDialogOpen, setNewLayoutDialogOpen] = useState(false);
    const [templateName, setTemplateName] = useState('');
    const [templateDescription, setTemplateDescription] = useState('');
    const [newLayoutName, setNewLayoutName] = useState('');

    const { confirm, ConfirmDialog } = useConfirmDialog();
    const [attackGraphExpanded, setAttackGraphExpanded] = useState(false);

    // ── DnD sensors ──
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    // ── Load layout into local state ──
    const loadLayout = useCallback((layoutId: string | null) => {
        if (!layoutId) {
            setSelectedLayoutId(null);
            setLayoutName('');
            setSections([]);
            setSelectedSectionIdx(null);
            setIsDirty(false);
            return;
        }
        const layout = layouts.find(l => l.id === layoutId);
        if (!layout) return;
        setSelectedLayoutId(layout.id);
        setLayoutName(layout.name);
        setSections(
            layout.sections
                .sort((a, b) => a.sort_order - b.sort_order)
                .map(s => ({
                    localId: newLocalId(),
                    section_type: s.section_type,
                    title: s.title,
                    content: s.content,
                }))
        );
        setSelectedSectionIdx(null);
        setIsDirty(false);
    }, [layouts]);

    // Auto-select first layout on load
    useEffect(() => {
        if (layouts.length > 0 && !selectedLayoutId) {
            loadLayout(layouts[0].id);
        }
    }, [layouts, selectedLayoutId, loadLayout]);

    // ── Handlers ──
    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (over && active.id !== over.id) {
            setSections(prev => {
                const oldIdx = prev.findIndex(s => s.localId === active.id);
                const newIdx = prev.findIndex(s => s.localId === over.id);
                const updated = arrayMove(prev, oldIdx, newIdx);
                return updated;
            });
            setIsDirty(true);
            // Adjust selected index
            if (selectedSectionIdx !== null) {
                const selectedLocalId = sections[selectedSectionIdx]?.localId;
                if (selectedLocalId) {
                    setSections(prev => {
                        const newIdx = prev.findIndex(s => s.localId === selectedLocalId);
                        setSelectedSectionIdx(newIdx >= 0 ? newIdx : null);
                        return prev;
                    });
                }
            }
        }
    };

    const addSection = (sectionType: SectionType) => {
        const title = sectionType === SectionType.TEXT
            ? 'New Section'
            : sectionType === SectionType.FINDINGS
                ? 'Findings'
                : sectionType === SectionType.TESTCASES
                    ? 'Test Cases'
                    : 'Cleanup Artifacts';
        const newSection: LocalSection = {
            localId: newLocalId(),
            section_type: sectionType,
            title,
            content: '',
        };
        setSections(prev => [...prev, newSection]);
        setSelectedSectionIdx(sections.length);
        setIsDirty(true);
    };

    const deleteSection = async (idx: number) => {
        const confirmed = await confirm({
            title: 'Remove Section',
            description: `Remove "${sections[idx]?.title || 'Untitled'}" from this layout?`,
            confirmLabel: 'Remove',
            variant: 'destructive',
        });
        if (!confirmed) return;
        setSections(prev => prev.filter((_, i) => i !== idx));
        if (selectedSectionIdx === idx) setSelectedSectionIdx(null);
        else if (selectedSectionIdx !== null && selectedSectionIdx > idx) setSelectedSectionIdx(selectedSectionIdx - 1);
        setIsDirty(true);
    };

    const updateSectionTitle = (idx: number, title: string) => {
        setSections(prev => prev.map((s, i) => i === idx ? { ...s, title } : s));
        setIsDirty(true);
    };

    const updateSectionContent = (idx: number, content: string) => {
        setSections(prev => prev.map((s, i) => i === idx ? { ...s, content } : s));
        setIsDirty(true);
    };

    const handleSave = async () => {
        if (!layoutName.trim()) {
            toast.error('Please enter a layout name');
            return;
        }
        const sectionPayload = sections.map((s, i) => ({
            section_type: s.section_type as 'text' | 'findings' | 'testcases' | 'cleanup_artifacts',
            title: s.title,
            content: s.content,
            sort_order: i,
        }));
        try {
            if (selectedLayoutId) {
                await updateLayout.mutateAsync({
                    engagementId,
                    layoutId: selectedLayoutId,
                    name: layoutName,
                    sections: sectionPayload,
                });
                toast.success('Layout saved');
            } else {
                const created = await createLayout.mutateAsync({
                    engagementId,
                    name: layoutName,
                    sections: sectionPayload,
                });
                setSelectedLayoutId(created.id);
                toast.success('Layout created');
            }
            setIsDirty(false);
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to save layout'));
        }
    };

    const handleDeleteLayout = async () => {
        if (!selectedLayoutId) return;
        const confirmed = await confirm({
            title: 'Delete Layout',
            description: `Delete "${layoutName}"? This cannot be undone.`,
            confirmLabel: 'Delete',
            variant: 'destructive',
        });
        if (!confirmed) return;
        try {
            await deleteLayout.mutateAsync({ engagementId, layoutId: selectedLayoutId });
            setSelectedLayoutId(null);
            setLayoutName('');
            setSections([]);
            setSelectedSectionIdx(null);
            setIsDirty(false);
            toast.success('Layout deleted');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to delete layout'));
        }
    };

    const handleImportTemplate = async (templateId: string) => {
        try {
            const imported = await importFromTemplate.mutateAsync({ engagementId, templateId });
            loadLayout(imported.id);
            setImportDialogOpen(false);
            toast.success('Layout imported from template');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to import template'));
        }
    };

    const handleSaveAsTemplate = async () => {
        if (!templateName.trim()) {
            toast.error('Enter a template name');
            return;
        }
        try {
            await saveAsTemplate.mutateAsync({
                name: templateName,
                description: templateDescription || undefined,
                sections: sections.map((s, i) => ({
                    section_type: s.section_type as 'text' | 'findings' | 'testcases' | 'cleanup_artifacts',
                    title: s.title,
                    content: s.content,
                    sort_order: i,
                })),
            });
            setSaveTemplateDialogOpen(false);
            setTemplateName('');
            setTemplateDescription('');
            toast.success('Saved as template');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to save template'));
        }
    };

    const handleCreateNewLayout = async () => {
        if (!newLayoutName.trim()) {
            toast.error('Enter a layout name');
            return;
        }
        try {
            const created = await createLayout.mutateAsync({
                engagementId,
                name: newLayoutName,
                sections: [],
            });
            // Set state directly from the response (cache hasn't refetched yet)
            setSelectedLayoutId(created.id);
            setLayoutName(created.name);
            setSections([]);
            setSelectedSectionIdx(null);
            setIsDirty(false);
            setNewLayoutDialogOpen(false);
            setNewLayoutName('');
            toast.success('New layout created');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to create layout'));
        }
    };

    // Clean up blob URL on unmount or when preview closes
    const cleanupPreview = useCallback(() => {
        if (previewBlobUrl) {
            window.URL.revokeObjectURL(previewBlobUrl);
            setPreviewBlobUrl(null);
        }
    }, [previewBlobUrl]);

    const handleGenerateReport = async () => {
        if (!selectedLayoutId) {
            toast.error('Please select a report layout first');
            return;
        }
        setIsGenerating(true);
        try {
            const result = await generateReport.mutateAsync({
                engagement_id: engagementId,
                layout_id: selectedLayoutId,
                report_format: format,
                exclude_severities: [],
                theme_id: selectedThemeId || undefined,
                include_evidence: format === 'json_zip' ? includeEvidence : undefined,
                finding_ids: selectedFindingIds ? Array.from(selectedFindingIds) : undefined,
                testcase_ids: selectedTestcaseIds ? Array.from(selectedTestcaseIds) : undefined,
                cleanup_ids: selectedCleanupIds ? Array.from(selectedCleanupIds) : undefined,
            });
            setLastGenerated(new Date().toLocaleTimeString());

            // Store result and open preview
            setPreviewResult(result);
            // Create blob URL for iframe/preview
            cleanupPreview();
            const url = window.URL.createObjectURL(result.blob);
            setPreviewBlobUrl(url);
            setPreviewOpen(true);
        } catch (error) {
            toast.error('Failed to generate report. Please check if findings exist.');
        } finally {
            setIsGenerating(false);
        }
    };

    const handlePreviewDownload = () => {
        if (previewResult) {
            downloadBlob(previewResult.blob, previewResult.filename);
            toast.success('Report downloaded');
        }
    };

    const handleSaveToEngagement = async () => {
        if (!previewResult) return;
        setIsSaving(true);
        try {
            await saveToEngagement.mutateAsync({
                blob: previewResult.blob,
                filename: previewResult.filename,
                engagementId,
            });
            toast.success('Report saved to engagement attachments', {
                action: {
                    label: 'View Attachments',
                    onClick: () => {
                        window.location.hash = '';
                        const params = new URLSearchParams(window.location.search);
                        params.set('tab', 'attachments');
                        window.history.replaceState(null, '', `${window.location.pathname}?${params}`);
                        window.location.reload();
                    },
                },
            });
        } catch (err) {
            toast.error('Failed to save report to engagement');
        } finally {
            setIsSaving(false);
        }
    };

    const handleClosePreview = () => {
        setPreviewOpen(false);
        cleanupPreview();
        setPreviewResult(null);
    };

    const selectedSection = selectedSectionIdx !== null ? sections[selectedSectionIdx] : null;

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* ─── Presence ─── */}
            {activeUsers.length > 0 && (
                <div className="flex justify-end">
                    <PresenceIndicator users={activeUsers} />
                </div>
            )}

            {/* ─── Attack Graph ─── */}
            <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-md overflow-hidden relative">
                <div className="absolute top-0 right-0 w-64 h-64 bg-rose-500/5 rounded-full blur-3xl -mr-32 -mt-32" />
                <CardHeader
                    className="cursor-pointer select-none"
                    onClick={() => setAttackGraphExpanded(!attackGraphExpanded)}
                >
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
                                <Network className="h-5 w-5 text-rose-400" />
                            </div>
                            <div>
                                <CardTitle className="text-xl font-bold text-white">Attack Graph</CardTitle>
                                <CardDescription className="text-slate-400">
                                    Visual map of assets, test cases, findings & cleanup items
                                </CardDescription>
                            </div>
                        </div>
                        <ChevronDown className={`h-5 w-5 text-slate-500 transition-transform duration-200 ${attackGraphExpanded ? '' : '-rotate-90'}`} />
                    </div>
                </CardHeader>
                {attackGraphExpanded && (
                    <CardContent className="relative">
                        <AttackGraph engagementId={engagementId} />
                    </CardContent>
                )}
            </Card>

            {/* ─── Report Builder ─── */}
            <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-md overflow-hidden relative">
                <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-3xl -mr-32 -mt-32" />
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                                <LayoutTemplate className="h-5 w-5 text-indigo-400" />
                            </div>
                            <div>
                                <CardTitle className="text-xl font-bold text-white">Report Builder</CardTitle>
                                <CardDescription className="text-slate-400">
                                    Build your report layout with drag-and-drop sections
                                </CardDescription>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4 relative">
                    {/* Layout Selector Row */}
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex-1 min-w-[200px]">
                            <Select
                                value={selectedLayoutId || ''}
                                onValueChange={(v) => loadLayout(v)}
                            >
                                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-10">
                                    <SelectValue placeholder={layoutsLoading ? 'Loading...' : 'Select a layout'} />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    {layouts.map(l => (
                                        <SelectItem key={l.id} value={l.id} className="focus:bg-indigo-500/20 focus:text-indigo-400">
                                            {l.name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5"
                            onClick={() => setNewLayoutDialogOpen(true)}
                            disabled={!canGenerateReport}
                        >
                            <Plus className="h-3.5 w-3.5" /> New Layout
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5"
                            onClick={() => setImportDialogOpen(true)}
                            disabled={!canGenerateReport}
                        >
                            <Import className="h-3.5 w-3.5" /> Import Template
                        </Button>
                    </div>

                    {/* Layout Name */}
                    {selectedLayoutId && (
                        <div className="space-y-1.5">
                            <Label className="text-xs text-slate-400 uppercase tracking-wide">Layout Name</Label>
                            <Input
                                value={layoutName}
                                onChange={e => { setLayoutName(e.target.value); setIsDirty(true); }}
                                className="bg-slate-950/50 border-slate-800 text-white h-9"
                                disabled={!canGenerateReport}
                            />
                        </div>
                    )}

                    {/* Two-column builder */}
                    {(selectedLayoutId || sections.length > 0) && (
                        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
                            {/* Left: Section List */}
                            <div className="lg:col-span-2 space-y-3">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider">Sections</h3>
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5 h-8"
                                                disabled={!canGenerateReport}
                                            >
                                                <Plus className="h-3.5 w-3.5" /> Add <ChevronDown className="h-3 w-3" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end" className="bg-slate-900 border-slate-800 text-slate-300">
                                            <DropdownMenuItem onClick={() => addSection(SectionType.TEXT)} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer gap-2">
                                                <Type className="h-4 w-4 text-blue-400" /> Text Section
                                            </DropdownMenuItem>
                                            <DropdownMenuSeparator className="bg-slate-800" />
                                            <DropdownMenuItem onClick={() => addSection(SectionType.FINDINGS)} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer gap-2">
                                                <Search className="h-4 w-4 text-amber-400" /> Findings Placeholder
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => addSection(SectionType.TESTCASES)} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer gap-2">
                                                <ClipboardList className="h-4 w-4 text-emerald-400" /> Test Cases Placeholder
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => addSection(SectionType.CLEANUP_ARTIFACTS)} className="hover:bg-slate-800 focus:bg-slate-800 cursor-pointer gap-2">
                                                <Sparkles className="h-4 w-4 text-lime-400" /> Cleanup Artifacts Placeholder
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>

                                {sections.length === 0 ? (
                                    <div className="text-center py-12 border border-dashed border-slate-800 rounded-lg">
                                        <LayoutTemplate className="h-10 w-10 mx-auto text-slate-700 mb-3" />
                                        <p className="text-sm text-slate-500">No sections yet</p>
                                        <p className="text-xs text-slate-600 mt-1">Click "Add" to build your report layout</p>
                                    </div>
                                ) : (
                                    <DndContext
                                        sensors={sensors}
                                        collisionDetection={closestCenter}
                                        onDragEnd={handleDragEnd}
                                    >
                                        <SortableContext items={sections.map(s => s.localId)} strategy={verticalListSortingStrategy}>
                                            <div className="space-y-2">
                                                {sections.map((section, idx) => (
                                                    <SortableSectionCard
                                                        key={section.localId}
                                                        section={section}
                                                        isSelected={selectedSectionIdx === idx}
                                                        onClick={() => setSelectedSectionIdx(idx)}
                                                        onDelete={() => deleteSection(idx)}
                                                    />
                                                ))}
                                            </div>
                                        </SortableContext>
                                    </DndContext>
                                )}
                            </div>

                            {/* Right: Section Editor */}
                            <div className="lg:col-span-3">
                                {selectedSection ? (
                                    <div className="space-y-4 p-4 rounded-lg border border-slate-800 bg-slate-950/30">
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-slate-400 uppercase tracking-wide">Section Title</Label>
                                            <Input
                                                value={selectedSection.title}
                                                onChange={e => updateSectionTitle(selectedSectionIdx!, e.target.value)}
                                                className="bg-slate-950/50 border-slate-800 text-white h-9"
                                                disabled={!canGenerateReport}
                                            />
                                        </div>

                                        {selectedSection.section_type === SectionType.TEXT ? (
                                            <div className="space-y-1.5">
                                                <Label className="text-xs text-slate-400 uppercase tracking-wide">Content</Label>
                                                <TiptapEditor
                                                    value={selectedSection.content}
                                                    onChange={val => updateSectionContent(selectedSectionIdx!, val)}
                                                    placeholder="Write your section content here..."
                                                    minHeight="250px"
                                                    disabled={!canGenerateReport}
                                                />
                                            </div>
                                        ) : (() => {
                                            // Multi-select item lists for placeholder sections
                                            const isFindings = selectedSection.section_type === SectionType.FINDINGS;
                                            const isTestcases = selectedSection.section_type === SectionType.TESTCASES;
                                            const items = isFindings ? allFindings : isTestcases ? allTestCases : allCleanup;
                                            const selectedIds = isFindings ? selectedFindingIds : isTestcases ? selectedTestcaseIds : selectedCleanupIds;
                                            const setSelectedIds = isFindings ? setSelectedFindingIds : isTestcases ? setSelectedTestcaseIds : setSelectedCleanupIds;
                                            const allSelected = selectedIds === null;
                                            const selectedCount = allSelected ? items.length : selectedIds.size;
                                            const colorClasses = isFindings
                                                ? { icon: 'text-amber-400/70', badge: 'border-amber-500/30 text-amber-400' }
                                                : isTestcases
                                                    ? { icon: 'text-emerald-400/70', badge: 'border-emerald-500/30 text-emerald-400' }
                                                    : { icon: 'text-lime-400/70', badge: 'border-lime-500/30 text-lime-400' };
                                            const Icon = isFindings ? Search : isTestcases ? ClipboardList : Sparkles;
                                            const label = isFindings ? 'Findings' : isTestcases ? 'Test Cases' : 'Cleanup Artifacts';

                                            const toggleItem = (id: string) => {
                                                if (allSelected) {
                                                    // Switch from "all" to explicit set minus this item
                                                    const newSet = new Set(items.map((i: any) => i.id));
                                                    newSet.delete(id);
                                                    setSelectedIds(newSet);
                                                } else {
                                                    const newSet = new Set(selectedIds);
                                                    if (newSet.has(id)) newSet.delete(id);
                                                    else newSet.add(id);
                                                    // If all items are selected again, revert to null (all)
                                                    if (newSet.size === items.length) setSelectedIds(null);
                                                    else setSelectedIds(newSet);
                                                }
                                            };

                                            const toggleAll = () => {
                                                if (allSelected) setSelectedIds(new Set());
                                                else setSelectedIds(null);
                                            };

                                            const isItemSelected = (id: string) => allSelected || selectedIds.has(id);

                                            const severityBadge = (severity: string) => {
                                                const colors: Record<string, string> = {
                                                    CRITICAL: 'bg-red-500/20 text-red-400',
                                                    HIGH: 'bg-orange-500/20 text-orange-400',
                                                    MEDIUM: 'bg-yellow-500/20 text-yellow-400',
                                                    LOW: 'bg-blue-500/20 text-blue-400',
                                                    INFO: 'bg-slate-500/20 text-slate-400',
                                                };
                                                return <Badge className={cn('text-[9px] h-4 px-1.5 border-none', colors[severity] || 'bg-slate-500/20 text-slate-400')}>{severity}</Badge>;
                                            };

                                            const statusBadge = (status: string) => {
                                                const colors: Record<string, string> = {
                                                    PENDING: 'bg-amber-500/20 text-amber-400',
                                                    CLEANED: 'bg-emerald-500/20 text-emerald-400',
                                                    PARTIALLY_CLEANED: 'bg-yellow-500/20 text-yellow-400',
                                                    NOT_APPLICABLE: 'bg-slate-500/20 text-slate-400',
                                                };
                                                return <Badge className={cn('text-[9px] h-4 px-1.5 border-none', colors[status] || 'bg-slate-500/20 text-slate-400')}>{status.replace(/_/g, ' ')}</Badge>;
                                            };

                                            return (
                                                <div className="rounded-lg border border-slate-700 bg-slate-900/50 overflow-hidden">
                                                    {/* Header */}
                                                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 bg-slate-900/80">
                                                        <div className="flex items-center gap-2">
                                                            <Icon className={cn('h-4 w-4', colorClasses.icon)} />
                                                            <span className="text-xs font-semibold text-slate-300">{label} to Include</span>
                                                            <Badge variant="outline" className={cn('text-[10px] h-5 px-1.5', colorClasses.badge)}>
                                                                {selectedCount}/{items.length}
                                                            </Badge>
                                                        </div>
                                                        <Button
                                                            size="sm"
                                                            variant="ghost"
                                                            className="h-6 px-2 text-[10px] text-slate-400 hover:text-white"
                                                            onClick={toggleAll}
                                                        >
                                                            {allSelected ? 'Deselect All' : 'Select All'}
                                                        </Button>
                                                    </div>
                                                    {/* Item list */}
                                                    <div className="max-h-[300px] overflow-y-auto">
                                                        {items.length === 0 ? (
                                                            <div className="p-6 text-center">
                                                                <p className="text-xs text-slate-500">No {label.toLowerCase()} found for this engagement</p>
                                                            </div>
                                                        ) : (
                                                            <div className="divide-y divide-slate-800/50">
                                                                {items.map((item: any) => (
                                                                    <label
                                                                        key={item.id}
                                                                        className="flex items-center gap-3 px-4 py-2 hover:bg-slate-800/40 cursor-pointer transition-colors"
                                                                    >
                                                                        <Checkbox
                                                                            checked={isItemSelected(item.id)}
                                                                            onCheckedChange={() => toggleItem(item.id)}
                                                                            className="border-slate-600 data-[state=checked]:bg-primary data-[state=checked]:border-indigo-600"
                                                                        />
                                                                        <div className="flex-1 min-w-0">
                                                                            <p className="text-xs font-medium text-white truncate">{item.title}</p>
                                                                            {isFindings && item.category && (
                                                                                <p className="text-[10px] text-slate-500 truncate">{item.category}</p>
                                                                            )}
                                                                        </div>
                                                                        {isFindings && item.severity && severityBadge(item.severity)}
                                                                        {!isFindings && !isTestcases && item.status && statusBadge(item.status)}
                                                                        {isTestcases && item.category && (
                                                                            <span className="text-[10px] text-slate-500 shrink-0">{item.category}</span>
                                                                        )}
                                                                    </label>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center h-full min-h-[300px] rounded-lg border border-dashed border-slate-800">
                                        <div className="text-center">
                                            <FileText className="h-10 w-10 mx-auto text-slate-700 mb-3" />
                                            <p className="text-sm text-slate-500">Select a section to edit</p>
                                            <p className="text-xs text-slate-600 mt-1">Click on a section in the list to view and edit it</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Action bar */}
                    {selectedLayoutId && (
                        <div className="flex items-center justify-between pt-4 border-t border-slate-800/50">
                            <div className="flex items-center gap-2">
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5"
                                    onClick={() => {
                                        setTemplateName(layoutName);
                                        setSaveTemplateDialogOpen(true);
                                    }}
                                    disabled={sections.length === 0}
                                >
                                    <Upload className="h-3.5 w-3.5" /> Save as Template
                                </Button>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    className="text-red-400 hover:text-red-300 hover:bg-red-500/10 gap-1.5"
                                    onClick={handleDeleteLayout}
                                    disabled={!canGenerateReport}
                                >
                                    <Trash2 className="h-3.5 w-3.5" /> Delete Layout
                                </Button>
                            </div>
                            <Button
                                onClick={handleSave}
                                disabled={!isDirty || !canGenerateReport || updateLayout.isPending || createLayout.isPending}
                                className={cn(
                                    'bg-primary hover:bg-primary/90 text-white gap-1.5 h-9 px-4 rounded-lg transition-all shadow-lg shadow-primary/20',
                                    !isDirty && 'opacity-50',
                                )}
                            >
                                {(updateLayout.isPending || createLayout.isPending) ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Save className="h-4 w-4" />
                                )}
                                Save Layout
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* ─── Report Generation (existing) ─── */}
            <div className="grid gap-6 md:grid-cols-3">
                <Card className="md:col-span-2 border-slate-800 bg-slate-900/40 backdrop-blur-md overflow-hidden relative">
                    <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-3xl -mr-32 -mt-32" />
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                                <FileText className="h-5 w-5 text-indigo-400" />
                            </div>
                            <div>
                                <CardTitle className="text-xl font-bold text-white">Generate Report</CardTitle>
                                <CardDescription className="text-slate-400">Configure and download your assessment report</CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-6 relative">
                        <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-300">Report Format</label>
                            <Select value={format} onValueChange={(v: any) => setFormat(v)}>
                                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-11">
                                    <SelectValue placeholder="Select format" />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    <SelectItem value="pdf" className="focus:bg-indigo-500/20 focus:text-indigo-400">PDF Document (.pdf)</SelectItem>
                                    <SelectItem value="markdown" className="focus:bg-indigo-500/20 focus:text-indigo-400">Markdown File (.md)</SelectItem>
                                    <SelectItem value="json_zip" className="focus:bg-indigo-500/20 focus:text-indigo-400">
                                        JSON Export (.zip)
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-slate-500">
                                {format === 'json_zip'
                                    ? 'Exports engagement data as JSON with evidence attachments in a ZIP archive'
                                    : 'PDF is recommended for final delivery'}
                            </p>
                        </div>

                        {format === 'json_zip' && (
                            <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-950/30 border border-slate-800/50">
                                <label className="flex items-center gap-2.5 cursor-pointer group">
                                    <div className="relative">
                                        <input
                                            type="checkbox"
                                            checked={includeEvidence}
                                            onChange={e => setIncludeEvidence(e.target.checked)}
                                            className="peer sr-only"
                                        />
                                        <div className="w-9 h-5 rounded-full bg-slate-700 peer-checked:bg-indigo-600 transition-colors" />
                                        <div className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm peer-checked:translate-x-4 transition-transform" />
                                    </div>
                                    <div>
                                        <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors flex items-center gap-1.5">
                                            <Package className="h-3.5 w-3.5 text-indigo-400" />
                                            Include Attachments
                                        </span>
                                        <p className="text-xs text-slate-500">Bundle evidence files marked for report inclusion</p>
                                    </div>
                                </label>
                            </div>
                        )}

                        <div className="space-y-2">
                            <label className="text-sm font-medium text-slate-300 flex items-center gap-1.5">
                                <Palette className="h-3.5 w-3.5 text-indigo-400" /> Report Theme
                            </label>
                            <Select value={selectedThemeId || '_none'} onValueChange={(v) => setSelectedThemeId(v === '_none' ? null : v)}>
                                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-11">
                                    <SelectValue placeholder="No theme (defaults)" />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    <SelectItem value="_none" className="focus:bg-indigo-500/20 focus:text-indigo-400">No theme (defaults)</SelectItem>
                                    {themes.map(t => (
                                        <SelectItem key={t.id} value={t.id} className="focus:bg-indigo-500/20 focus:text-indigo-400">
                                            <span className="flex items-center gap-2">
                                                <span className="inline-block w-3 h-3 rounded-full border border-slate-700" style={{ backgroundColor: t.primary_color }} />
                                                {t.name}
                                            </span>
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-slate-500">Controls colors, fonts, logo, and page settings</p>
                        </div>

                        {selectedLayoutId ? (
                            <div className="bg-slate-950/30 rounded-xl p-4 border border-slate-800/50 space-y-2">
                                <p className="text-xs text-slate-400">
                                    <span className="font-medium text-slate-300">Layout:</span> {layoutName}
                                </p>
                                <p className="text-xs text-slate-500">
                                    {sections.length} section{sections.length !== 1 ? 's' : ''} will be rendered in order
                                </p>
                            </div>
                        ) : (
                            <div className="bg-amber-500/5 rounded-xl p-4 border border-amber-500/20 flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                                <p className="text-xs text-amber-400/80">Select or create a layout above to generate a report.</p>
                            </div>
                        )}

                        <div className="flex items-center justify-between pt-4 border-t border-slate-800/50">
                            <div className="text-xs text-slate-500">
                                {lastGenerated && (
                                    <span className="flex items-center gap-1.5">
                                        <CheckCircle className="h-3 w-3 text-emerald-500" />
                                        Last generated at {lastGenerated}
                                    </span>
                                )}
                            </div>
                            <Button
                                onClick={handleGenerateReport}
                                disabled={isGenerating || !canGenerateReport || !selectedLayoutId}
                                className={cn(
                                    'bg-primary hover:bg-primary/90 text-white min-w-[160px] h-11 rounded-lg transition-all duration-300 shadow-lg shadow-primary/20',
                                    (!canGenerateReport || !selectedLayoutId) && 'opacity-50 cursor-not-allowed',
                                )}
                            >
                                {isGenerating ? (
                                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating...</>
                                ) : (
                                    <><Eye className="h-4 w-4 mr-2" /> Generate &amp; Preview</>
                                )}
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Info Card */}
                <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-md border-l-4 border-l-amber-500/40">
                    <CardHeader>
                        <CardTitle className="text-sm font-bold text-amber-500 uppercase tracking-tight flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4" /> Pre-flight Check
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <p className="text-xs text-slate-400 leading-relaxed">
                            Ensure all findings are reviewed and validated before generating the final report.
                            The report will include all "Verified" and "Open" findings by default.
                        </p>
                        <Separator className="bg-slate-800/50" />
                        <div className="space-y-3">
                            <h5 className="text-[10px] font-bold text-slate-500 uppercase">Quick Tips</h5>
                            <ul className="space-y-2 text-xs text-slate-400">
                                <li className="flex items-start gap-2"><CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" /> Build your layout above with text sections for intro, scope, conclusion, etc.</li>
                                <li className="flex items-start gap-2"><CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" /> Add a Findings placeholder where findings should appear.</li>
                                <li className="flex items-start gap-2"><CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" /> Save layouts as templates for reuse across engagements.</li>
                            </ul>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* ─── Import Template Dialog ─── */}
            <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Import className="h-5 w-5 text-indigo-400" /> Import from Template
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Select a report layout template to import as a new layout for this engagement.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2 max-h-[300px] overflow-y-auto py-2">
                        {templates.length === 0 ? (
                            <p className="text-sm text-slate-500 text-center py-8">No templates available. Create one on the Templates page.</p>
                        ) : (
                            templates.map(t => (
                                <div
                                    key={t.id}
                                    className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-900/40 hover:bg-slate-800/50 cursor-pointer transition-colors"
                                    onClick={() => handleImportTemplate(t.id)}
                                >
                                    <div>
                                        <p className="text-sm font-medium text-white">{t.name}</p>
                                        {t.description && <p className="text-xs text-slate-400 mt-0.5">{t.description}</p>}
                                    </div>
                                    <Badge variant="secondary" className="text-xs">{t.sections.length} sections</Badge>
                                </div>
                            ))
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setImportDialogOpen(false)}>Cancel</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* ─── Save as Template Dialog ─── */}
            <Dialog open={saveTemplateDialogOpen} onOpenChange={setSaveTemplateDialogOpen}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Upload className="h-5 w-5 text-indigo-400" /> Save as Template
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Save this layout as a reusable template for other engagements.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Template Name</Label>
                            <Input
                                value={templateName}
                                onChange={e => setTemplateName(e.target.value)}
                                placeholder="e.g. Standard Pentest Report"
                                className="bg-slate-950/50 border-slate-800 text-white"
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Description (optional)</Label>
                            <Input
                                value={templateDescription}
                                onChange={e => setTemplateDescription(e.target.value)}
                                placeholder="A brief description of this template"
                                className="bg-slate-950/50 border-slate-800 text-white"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setSaveTemplateDialogOpen(false)}>Cancel</Button>
                        <Button
                            onClick={handleSaveAsTemplate}
                            disabled={!templateName.trim() || saveAsTemplate.isPending}
                            className="bg-primary hover:bg-primary/90"
                        >
                            {saveAsTemplate.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                            Save Template
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* ─── New Layout Dialog ─── */}
            <Dialog open={newLayoutDialogOpen} onOpenChange={setNewLayoutDialogOpen}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="text-white">Create New Layout</DialogTitle>
                        <DialogDescription className="text-slate-400">
                            Give your new report layout a name to get started.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="py-2">
                        <div className="space-y-1.5">
                            <Label className="text-slate-300">Layout Name</Label>
                            <Input
                                value={newLayoutName}
                                onChange={e => setNewLayoutName(e.target.value)}
                                placeholder="e.g. Final Report"
                                className="bg-slate-950/50 border-slate-800 text-white"
                                onKeyDown={e => { if (e.key === 'Enter') handleCreateNewLayout(); }}
                                autoFocus
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setNewLayoutDialogOpen(false)}>Cancel</Button>
                        <Button
                            onClick={handleCreateNewLayout}
                            disabled={!newLayoutName.trim() || createLayout.isPending}
                            className="bg-primary hover:bg-primary/90"
                        >
                            {createLayout.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                            Create
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <ConfirmDialog />

            {/* ─── Report Preview Dialog ─── */}
            <Dialog open={previewOpen} onOpenChange={(open) => { if (!open) handleClosePreview(); }}>
                <DialogContent className="max-w-5xl max-h-[90vh] flex flex-col">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Eye className="h-5 w-5 text-indigo-400" /> Report Preview
                        </DialogTitle>
                        <DialogDescription asChild>
                            <div className="text-sm text-slate-400 flex items-center gap-3">
                            {previewResult && (
                                <>
                                    <span className="font-medium text-slate-300">{previewResult.filename}</span>
                                    <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                                        {(previewResult.blob.size / 1024).toFixed(0)} KB
                                    </Badge>
                                    <Badge variant="outline" className={cn(
                                        'text-[10px]',
                                        format === 'pdf' ? 'border-red-500/30 text-red-400' :
                                        format === 'markdown' ? 'border-blue-500/30 text-blue-400' :
                                        'border-amber-500/30 text-amber-400'
                                    )}>
                                        {format === 'pdf' ? 'PDF' : format === 'markdown' ? 'Markdown' : 'JSON ZIP'}
                                    </Badge>
                                    {lastGenerated && (
                                        <span className="text-[10px] text-slate-500 flex items-center gap-1">
                                            <CheckCircle className="h-3 w-3 text-emerald-500" />
                                            Generated at {lastGenerated}
                                        </span>
                                    )}
                                </>
                            )}
                            </div>
                        </DialogDescription>
                    </DialogHeader>

                    {/* Preview Area */}
                    <div className="flex-1 min-h-0 rounded-lg border border-slate-800 bg-slate-950/50 overflow-hidden">
                        {format === 'pdf' && previewBlobUrl ? (
                            <iframe
                                src={previewBlobUrl}
                                className="w-full h-full min-h-[60vh]"
                                title="Report Preview"
                            />
                        ) : format === 'markdown' && previewResult ? (
                            <MarkdownPreview blob={previewResult.blob} />
                        ) : format === 'json_zip' && previewResult ? (
                            <div className="flex items-center justify-center h-full min-h-[300px]">
                                <div className="text-center space-y-4">
                                    <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 inline-block">
                                        <Archive className="h-12 w-12 text-amber-400" />
                                    </div>
                                    <div>
                                        <p className="text-lg font-bold text-white">JSON Export Archive</p>
                                        <p className="text-sm text-slate-400 mt-1">
                                            {previewResult.filename} · {(previewResult.blob.size / 1024).toFixed(0)} KB
                                        </p>
                                        <p className="text-xs text-slate-500 mt-2 max-w-sm">
                                            ZIP archive containing engagement data as JSON with evidence attachments.
                                            Download or save to engagement to access the contents.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center justify-center h-full min-h-[300px]">
                                <Loader2 className="h-8 w-8 text-slate-500 animate-spin" />
                            </div>
                        )}
                    </div>

                    {/* Action Buttons */}
                    <DialogFooter className="flex items-center justify-between sm:justify-between gap-2 pt-2">
                        <Button
                            variant="ghost"
                            onClick={handleClosePreview}
                            className="text-slate-400 hover:text-white"
                        >
                            <X className="h-4 w-4 mr-1.5" /> Close
                        </Button>
                        <div className="flex items-center gap-2">
                            <Button
                                variant="outline"
                                onClick={handleSaveToEngagement}
                                disabled={isSaving}
                                className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5"
                            >
                                {isSaving ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Paperclip className="h-4 w-4" />
                                )}
                                Save to Engagement
                            </Button>
                            <Button
                                onClick={handlePreviewDownload}
                                className="bg-primary hover:bg-primary/90 text-white gap-1.5 shadow-lg shadow-primary/20"
                            >
                                <Download className="h-4 w-4" /> Download
                            </Button>
                        </div>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div >
    );
}

const Separator = ({ className }: { className?: string }) => (
    <div className={cn("h-px w-full", className)} />
);


// ── Markdown Preview Component ──────────────────────────────────
// Reads the blob as text and renders it in a styled scrollable container.
// Uses a simple HTML conversion approach (no external dependency).
function MarkdownPreview({ blob }: { blob: Blob }) {
    const [content, setContent] = useState<string>('');

    useEffect(() => {
        blob.text().then(setContent);
    }, [blob]);

    if (!content) {
        return (
            <div className="flex items-center justify-center h-full min-h-[300px]">
                <Loader2 className="h-8 w-8 text-slate-500 animate-spin" />
            </div>
        );
    }

    return (
        <div className="overflow-auto max-h-[60vh] p-6">
            <pre className="whitespace-pre-wrap font-mono text-sm text-slate-300 leading-relaxed">
                {content}
            </pre>
        </div>
    );
}
