/**
 * templates/report-layouts/[id]/edit/page.tsx — Report Layout Editor
 *
 * Visual section builder for report layout templates. Two-panel layout:
 *
 * **Left panel** — sortable (drag-and-drop via `@dnd-kit`) list of
 *   sections. Each section has a type badge (Text / Findings / Test
 *   Cases / Cleanup Artifacts), a title, and a delete button.
 *   "Add" dropdown adds new sections of any type.
 *
 * **Right panel** — section editor. Text sections use `TiptapEditor`
 *   for rich WYSIWYG content. Placeholder sections show an info card.
 *
 * Top card: template name and optional description.
 * Route `[id]=new` creates a new template; otherwise loads existing.
 * Saves redirect to `/templates?tab=report-layouts`.
 *
 * Sub-components: `SortableSectionCard`.
 * Types: `LocalSection`, `SectionType`.
 */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
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
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
    DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
    ArrowLeft, Plus, GripVertical, Trash2, Save, Loader2,
    LayoutTemplate, Type, Search, ClipboardList, ChevronDown, Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    useReportLayoutTemplate,
    useCreateReportLayoutTemplate,
    useUpdateReportLayoutTemplate,
} from '@/lib/hooks/use-report-layout-templates';
import { SectionType } from '@/lib/types';
import { toast } from 'sonner';
import { getErrorMessage } from '@/components/ui/confirm-dialog';
import dynamic from 'next/dynamic';

const TiptapEditor = dynamic(() => import('@/components/ui/tiptap-editor'), { ssr: false });

interface LocalSection {
    localId: string;
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
                    ? 'border-primary/50 bg-primary/10 shadow-lg shadow-primary/5'
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
// Main Editor Page
// ═══════════════════════════════════════════════════════════════════
export default function ReportLayoutTemplateEditPage() {
    const router = useRouter();
    const params = useParams();
    const templateId = params?.id as string;
    const isNew = templateId === 'new';

    const { data: existingTemplate, isLoading } = useReportLayoutTemplate(isNew ? undefined : templateId);
    const createTemplate = useCreateReportLayoutTemplate();
    const updateTemplate = useUpdateReportLayoutTemplate();

    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [sections, setSections] = useState<LocalSection[]>([]);
    const [selectedSectionIdx, setSelectedSectionIdx] = useState<number | null>(null);
    const [loaded, setLoaded] = useState(false);

    // DnD
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
    );

    // Load existing template data
    useEffect(() => {
        if (existingTemplate && !loaded) {
            setName(existingTemplate.name);
            setDescription(existingTemplate.description || '');
            setSections(
                existingTemplate.sections
                    .sort((a, b) => a.sort_order - b.sort_order)
                    .map(s => ({
                        localId: newLocalId(),
                        section_type: s.section_type,
                        title: s.title,
                        content: s.content,
                    }))
            );
            setLoaded(true);
        }
    }, [existingTemplate, loaded]);

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (over && active.id !== over.id) {
            setSections(prev => {
                const oldIdx = prev.findIndex(s => s.localId === active.id);
                const newIdx = prev.findIndex(s => s.localId === over.id);
                return arrayMove(prev, oldIdx, newIdx);
            });
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
        setSections(prev => [...prev, { localId: newLocalId(), section_type: sectionType, title, content: '' }]);
        setSelectedSectionIdx(sections.length);
    };

    const removeSection = (idx: number) => {
        setSections(prev => prev.filter((_, i) => i !== idx));
        if (selectedSectionIdx === idx) setSelectedSectionIdx(null);
        else if (selectedSectionIdx !== null && selectedSectionIdx > idx) setSelectedSectionIdx(selectedSectionIdx - 1);
    };

    const updateSectionTitle = (idx: number, title: string) => {
        setSections(prev => prev.map((s, i) => i === idx ? { ...s, title } : s));
    };

    const updateSectionContent = (idx: number, content: string) => {
        setSections(prev => prev.map((s, i) => i === idx ? { ...s, content } : s));
    };

    const handleSave = async () => {
        if (!name.trim()) {
            toast.error('Please enter a template name');
            return;
        }
        const sectionPayload = sections.map((s, i) => ({
            section_type: s.section_type as 'text' | 'findings' | 'testcases' | 'cleanup_artifacts',
            title: s.title,
            content: s.content,
            sort_order: i,
        }));
        try {
            if (isNew) {
                await createTemplate.mutateAsync({
                    name,
                    description: description || undefined,
                    sections: sectionPayload,
                });
                toast.success('Template created');
            } else {
                await updateTemplate.mutateAsync({
                    id: templateId,
                    name,
                    description: description || undefined,
                    sections: sectionPayload,
                });
                toast.success('Template updated');
            }
            router.push('/templates?tab=report-layouts');
        } catch (err) {
            toast.error(getErrorMessage(err, 'Failed to save template'));
        }
    };

    const selectedSection = selectedSectionIdx !== null ? sections[selectedSectionIdx] : null;
    const isPending = createTemplate.isPending || updateTemplate.isPending;

    if (!isNew && isLoading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center h-96">
                    <Loader2 className="h-8 w-8 animate-spin text-slate-500" />
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
                        <Button
                            variant="ghost"
                            size="icon"
                            className="text-slate-400 hover:text-white"
                            onClick={() => router.push('/templates?tab=report-layouts')}
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-xl font-bold text-white flex items-center gap-2">
                                <LayoutTemplate className="h-5 w-5 text-primary" />
                                {isNew ? 'New Report Layout Template' : 'Edit Report Layout Template'}
                            </h1>
                            <p className="text-sm text-slate-400 mt-0.5">Define the sections and structure for your report</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            className="border-slate-700 text-slate-300"
                            onClick={() => router.push('/templates?tab=report-layouts')}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={handleSave}
                            disabled={isPending || !name.trim()}
                            className="bg-primary hover:bg-primary/90 text-white gap-2"
                        >
                            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                            {isNew ? 'Create' : 'Save'}
                        </Button>
                    </div>
                </div>

                {/* Name & Description */}
                <Card className="border-slate-800 bg-slate-900/40">
                    <CardContent className="p-5 space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <Label className="text-xs text-slate-400 uppercase tracking-wide">Template Name *</Label>
                                <Input
                                    value={name}
                                    onChange={e => setName(e.target.value)}
                                    placeholder="e.g. Standard Pentest Report"
                                    className="bg-slate-950/50 border-slate-800 text-white"
                                    autoFocus={isNew}
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-xs text-slate-400 uppercase tracking-wide">Description</Label>
                                <Input
                                    value={description}
                                    onChange={e => setDescription(e.target.value)}
                                    placeholder="Brief description of this template"
                                    className="bg-slate-950/50 border-slate-800 text-white"
                                />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Section Builder */}
                <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
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
                            <div className="text-center py-16 border border-dashed border-slate-800 rounded-lg">
                                <LayoutTemplate className="h-10 w-10 mx-auto text-slate-700 mb-3" />
                                <p className="text-sm text-slate-500">No sections yet</p>
                                <p className="text-xs text-slate-600 mt-1">Click "Add" to start building your template</p>
                            </div>
                        ) : (
                            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                                <SortableContext items={sections.map(s => s.localId)} strategy={verticalListSortingStrategy}>
                                    <div className="space-y-2">
                                        {sections.map((section, idx) => (
                                            <SortableSectionCard
                                                key={section.localId}
                                                section={section}
                                                isSelected={selectedSectionIdx === idx}
                                                onClick={() => setSelectedSectionIdx(idx)}
                                                onDelete={() => removeSection(idx)}
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
                            <Card className="border-slate-800 bg-slate-900/40">
                                <CardContent className="p-5 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-slate-400 uppercase tracking-wide">Section Title</Label>
                                        <Input
                                            value={selectedSection.title}
                                            onChange={e => updateSectionTitle(selectedSectionIdx!, e.target.value)}
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>

                                    {selectedSection.section_type === SectionType.TEXT ? (
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-slate-400 uppercase tracking-wide">Content</Label>
                                            <TiptapEditor
                                                value={selectedSection.content}
                                                onChange={val => updateSectionContent(selectedSectionIdx!, val)}
                                                placeholder="Write your section content here..."
                                                minHeight="350px"
                                            />
                                        </div>
                                    ) : (
                                        <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/50 p-8 text-center">
                                            {selectedSection.section_type === SectionType.FINDINGS ? (
                                                <>
                                                    <Search className="h-10 w-10 mx-auto text-amber-500/50 mb-2" />
                                                    <p className="text-sm font-medium text-amber-400/80">Findings Placeholder</p>
                                                    <p className="text-xs text-slate-500 mt-1">Engagement findings will appear here when this template is used.</p>
                                                </>
                                            ) : selectedSection.section_type === SectionType.TESTCASES ? (
                                                <>
                                                    <ClipboardList className="h-10 w-10 mx-auto text-emerald-500/50 mb-2" />
                                                    <p className="text-sm font-medium text-emerald-400/80">Test Cases Placeholder</p>
                                                    <p className="text-xs text-slate-500 mt-1">Engagement test cases will appear here when this template is used.</p>
                                                </>
                                            ) : (
                                                <>
                                                    <Sparkles className="h-10 w-10 mx-auto text-lime-500/50 mb-2" />
                                                    <p className="text-sm font-medium text-lime-400/80">Cleanup Artifacts Placeholder</p>
                                                    <p className="text-xs text-slate-500 mt-1">Engagement cleanup artifacts will appear here when this template is used.</p>
                                                </>
                                            )}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        ) : (
                            <div className="flex items-center justify-center h-full min-h-[400px] rounded-lg border border-dashed border-slate-800">
                                <div className="text-center">
                                    <LayoutTemplate className="h-12 w-12 mx-auto text-slate-700 mb-3" />
                                    <p className="text-sm text-slate-500">Select a section to edit</p>
                                    <p className="text-xs text-slate-600 mt-1">Click on a section in the list to view and edit it</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
}
