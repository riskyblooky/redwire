/**
 * testcases/[id]/edit/page.tsx — Edit Test Case Page
 *
 * Pre-populated edit form mirroring the create page layout (main column +
 * sidebar tag grid). Key differences from the create page:
 *  - Engagement field is read-only (cannot be changed after creation).
 *  - Parent test case selector allows re-nesting (filters out self and
 *    own children to prevent cycles).
 *  - Template application shows a caution warning about overwriting fields.
 *  - Category uses a keyed Select to re-render correctly after data load.
 *  - Tags are initialised from the test case's existing tag associations.
 */
'use client';

import { useParams } from '@/lib/hooks/use-params';
import { buildTestcaseContext } from '@/lib/ai-entity-context';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { useCustomFieldDefs } from '@/lib/hooks/use-custom-fields';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { TemplatePickerDialog } from '@/components/ui/template-picker-dialog';
import { ArrowLeft, Save, Loader2, Plus, ChevronsUpDown, BookOpen, CheckCircle2, XCircle, FileText, ListChecks, ListPlus } from 'lucide-react';
import { useTestCase, useUpdateTestCase, useTestCases } from '@/lib/hooks/use-testcases';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { toast } from 'sonner';
import { useTestCaseTemplates } from '@/lib/hooks/use-testcase-templates';
import { useTags } from '@/lib/hooks/use-tags';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useNavigationGuard } from '@/lib/hooks/use-navigation-guard';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { CustomFieldsForm } from '@/components/custom-fields/custom-fields-form';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';
import { useEngagementMarkingProfile } from '@/lib/hooks/use-marking-profiles';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { EditLockBanner } from '@/components/collaboration/edit-lock-banner';
import { VersionHistoryPanel } from '@/components/ui/version-history-panel';
import { useAuthStore } from '@/stores/auth-store';
import { apiErrorMessage } from '@/lib/api';


export default function EditTestCasePage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const returnEngagementId = searchParams?.get('engagementId');
    const returnTab = searchParams?.get('tab') || 'testcases';

    const { data: testcase, isLoading: isLoadingTC } = useTestCase(id);
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const { data: categories = [] } = useConfigurableTypes('testcase');
    const { data: tags = [], isLoading: isLoadingTags } = useTags('testcase');
    const updateTestCase = useUpdateTestCase();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // Live presence — same channel as the view page so editors and
    // viewers see each other. mode:'edit' tags this connection as
    // actively editing so other editors get warned.
    const currentUserId = useAuthStore(s => s.user?.id);
    const { activeUsers } = useCollaboration({
        resourceType: 'testcase',
        resourceId: id,
        enabled: !!testcase,
        mode: 'edit',
    });
    const otherEditors = activeUsers.filter(
        u => u.mode === 'edit' && u.id !== currentUserId
    );
    const hasConcurrentEditor = otherEditors.length > 0;
    const [templateOpen, setTemplateOpen] = useState(false);
    const [isDirty, setIsDirty] = useState(false);

    const getBackPath = () => returnEngagementId
        ? `/engagements/${returnEngagementId}?tab=${returnTab}`
        : `/testcases/${id}`;

    const { navigateWithGuard } = useNavigationGuard(isDirty, confirm);

    const [formData, setFormData] = useState({
        title: '',
        engagement_id: '',
        parent_id: '' as string | null,
        category: '',
        description: '',
        steps: '',
        expected_result: '',
        actual_result: '',
        is_executed: false,
        is_successful: null as boolean | null,
        notes: '',
        classification_level: '' as string,
        classification_suffix: '' as string,
        tag_ids: [] as string[],
        attack_technique_ids: [] as string[],
        custom_fields: {} as Record<string, unknown>,
    });
    const markingProfile = useEngagementMarkingProfile(formData.engagement_id);
    const { data: cfDefs = [] } = useCustomFieldDefs('testcase');
    const hasCustomFields = cfDefs.length > 0;

    useEffect(() => {
        if (testcase) {
            setFormData({
                title: testcase.title || '',
                engagement_id: testcase.engagement_id || '',
                parent_id: testcase.parent_id || null,
                category: testcase.category || '',
                description: testcase.description || '',
                steps: testcase.steps || '',
                expected_result: testcase.expected_result || '',
                actual_result: testcase.actual_result || '',
                is_executed: !!testcase.is_executed,
                is_successful: testcase.is_successful ?? null,
                notes: testcase.notes || '',
                classification_level: (testcase as any).classification_level || '',
                classification_suffix: (testcase as any).classification_suffix || '',
                tag_ids: testcase.tags?.map(t => t.id) || [],
                attack_technique_ids: testcase.attack_technique_ids || [],
                custom_fields: (testcase.custom_fields as Record<string, unknown>) || {},
            });
            setIsDirty(false);
        }
    }, [testcase]);

    const handleChange = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setIsDirty(true);
    };

    const applyTemplate = (template: any) => {
        if (template) {
            setFormData(prev => ({
                ...prev,
                title: template.title,
                category: template.category,
                description: template.description,
                steps: template.steps || '',
                expected_result: template.expected_result || '',
                attack_technique_ids: (template.attack_technique_ids?.length ?? 0) > 0
                    ? template.attack_technique_ids
                    : prev.attack_technique_ids,
            }));
            setIsDirty(true);
        }
    };

    const toggleTag = (tagId: string) => {
        setFormData(prev => {
            const current = [...prev.tag_ids];
            const index = current.indexOf(tagId);
            if (index > -1) {
                current.splice(index, 1);
            } else {
                current.push(tagId);
            }
            return { ...prev, tag_ids: current };
        });
        setIsDirty(true);
    };

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        try {
            await updateTestCase.mutateAsync({
                id: id,
                ...formData,
                classification_level: formData.classification_level || null,
                classification_suffix: formData.classification_suffix || null,
            });
            setIsDirty(false);
            router.push(`/testcases/${id}`);
        } catch (error: any) {
            console.error('Failed to update test case:', error);
            toast.error(apiErrorMessage(error, 'Failed to update test case'));
        }
    };

    // Fetch sibling test cases for parent selector (same engagement)
    const { data: engagementTestCases = [] } = useTestCases(testcase?.engagement_id);
    // Filter out self and own children to prevent cycles
    const availableParents = engagementTestCases.filter(tc => tc.id !== id && tc.parent_id !== id);

    if (isLoadingTC) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
          <div className="flex flex-col min-h-full">
            {/* ── Sticky header ── */}
            <div className="sticky top-0 z-20 bg-slate-950/90 backdrop-blur-md border-b border-slate-800/50">
                <div className="flex items-center justify-between px-6 pt-5 pb-4">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost" size="icon"
                            onClick={() => navigateWithGuard(getBackPath())}
                            className="text-slate-400 hover:text-white hover:bg-slate-800"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-2xl font-bold text-white tracking-tight">Edit Test Case</h1>
                            <p className="text-slate-400 text-sm mt-0.5 truncate">{testcase?.title}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 relative z-30">
                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                        {testcase && <VersionHistoryPanel entityType="testcase" entityId={id} currentData={testcase} />}
                        <div className="h-8 w-px bg-slate-800" />
                        <Button
                            type="button" variant="outline"
                            onClick={() => setTemplateOpen(true)}
                            className="bg-slate-900/50 border-slate-800 text-slate-300 hover:bg-slate-800 hover:text-white"
                        >
                            <BookOpen className="h-4 w-4 mr-2" />
                            Override with Template...
                        </Button>
                    </div>
                </div>
            </div>
            <TemplatePickerDialog
                open={templateOpen}
                onOpenChange={setTemplateOpen}
                resource="testcase"
                onSelect={applyTemplate}
                title="Select Test Case Template"
                description="This will overwrite current fields with the selected template."
            />

            <EditLockBanner otherEditors={otherEditors} />

            {/* Content */}
            <div className="p-6 pb-24 flex-1">
                <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-4">
                    <div className="lg:col-span-3">
                        <Tabs defaultValue="result" className="w-full">
                            <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1 w-full flex justify-start gap-1 rounded-xl h-12">
                                <TabsTrigger value="definition" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-blue-500/10 data-[state=active]:text-blue-400 font-semibold">
                                    <FileText className="h-4 w-4" /> Definition
                                </TabsTrigger>
                                <TabsTrigger value="result" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 font-semibold">
                                    <ListChecks className="h-4 w-4" /> Steps &amp; Result
                                </TabsTrigger>
                                {hasCustomFields && (
                                    <TabsTrigger value="custom" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-amber-500/10 data-[state=active]:text-amber-400 font-semibold">
                                        <ListPlus className="h-4 w-4" /> Custom Fields
                                    </TabsTrigger>
                                )}
                            </TabsList>

                            <div className="mt-6">
                                {/* ── Definition ── */}
                                <TabsContent value="definition">
                                    <Card className="border-slate-800 bg-slate-900/50">
                                        <CardContent className="space-y-6 pt-6">
                                            <div className="space-y-2">
                                                <Label className="text-slate-200">Engagement *</Label>
                                                {isLoadingTC || isLoadingEngagements ? (
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

                                            <div className="space-y-2">
                                                <Label className="text-slate-200">Parent Test Case</Label>
                                                <Select
                                                    value={formData.parent_id || '__none__'}
                                                    onValueChange={(val) => handleChange('parent_id', val === '__none__' ? null : val)}
                                                >
                                                    <SelectTrigger className="bg-slate-800/50 border-slate-700 text-white">
                                                        <SelectValue placeholder="None (root level)" />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                        <SelectItem value="__none__">None (root level)</SelectItem>
                                                        {availableParents.map((tc) => (
                                                            <SelectItem key={tc.id} value={tc.id}>{tc.title}</SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                                <p className="text-[10px] text-slate-500 italic">Nest this test case under another test case.</p>
                                            </div>

                                            <div className="space-y-2">
                                                <Label className="text-slate-200">Title *</Label>
                                                <Input value={formData.title} onChange={(e) => handleChange('title', e.target.value)} required className="bg-slate-800 border-slate-700 text-white" />
                                            </div>

                                            <div className="space-y-2">
                                                <Label className="text-slate-200">Category *</Label>
                                                <Select
                                                    key={`${testcase?.id}-${formData.category}`}
                                                    value={formData.category}
                                                    onValueChange={(val) => handleChange('category', val)}
                                                >
                                                    <SelectTrigger className="bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                        {categories.map((c) => <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>)}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-200">Description *</Label>
                                                <MarkdownEditor value={formData.description} onChange={(val) => handleChange('description', val)} minHeight="250px" fieldContext={{ resourceType: 'testcase', fieldName: 'Description', entityContext: buildTestcaseContext(formData) }} engagementId={formData.engagement_id} />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                {/* ── Steps & Execution Result ── */}
                                <TabsContent value="result">
                                    <Card className="border-slate-800 bg-slate-900/50">
                                        <CardContent className="space-y-6 pt-6">
                                            <div className="space-y-4">
                                                <Label className="text-slate-200">Steps</Label>
                                                <MarkdownEditor value={formData.steps} onChange={(val) => handleChange('steps', val)} minHeight="300px" fieldContext={{ resourceType: 'testcase', fieldName: 'Steps', entityContext: buildTestcaseContext(formData) }} engagementId={formData.engagement_id} />
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-200">Expected Result</Label>
                                                <MarkdownEditor value={formData.expected_result} onChange={(val) => handleChange('expected_result', val)} minHeight="150px" fieldContext={{ resourceType: 'testcase', fieldName: 'Expected Result', entityContext: buildTestcaseContext(formData) }} engagementId={formData.engagement_id} />
                                            </div>

                                            <div className="space-y-3 border-t border-slate-800 pt-5">
                                                <div className="flex items-center justify-between">
                                                    <div>
                                                        <Label className="text-slate-200">Executed</Label>
                                                        <p className="text-[10px] text-slate-500 italic mt-0.5">Has this test case been run?</p>
                                                    </div>
                                                    <Switch
                                                        checked={formData.is_executed}
                                                        onCheckedChange={(v) => { handleChange('is_executed', v); if (!v) handleChange('is_successful', null); }}
                                                    />
                                                </div>
                                                {formData.is_executed && (
                                                    <div className="flex items-center gap-2">
                                                        <button type="button" onClick={() => handleChange('is_successful', true)}
                                                            className={cn('flex-1 h-10 rounded-md border text-sm font-semibold flex items-center justify-center gap-2 transition-colors',
                                                                formData.is_successful === true ? 'bg-green-600/20 border-green-500/40 text-green-300' : 'bg-slate-950/40 border-slate-700 text-slate-400 hover:border-green-500/30')}>
                                                            <CheckCircle2 className="h-4 w-4" /> Pass
                                                        </button>
                                                        <button type="button" onClick={() => handleChange('is_successful', false)}
                                                            className={cn('flex-1 h-10 rounded-md border text-sm font-semibold flex items-center justify-center gap-2 transition-colors',
                                                                formData.is_successful === false ? 'bg-red-600/20 border-red-500/40 text-red-300' : 'bg-slate-950/40 border-slate-700 text-slate-400 hover:border-red-500/30')}>
                                                            <XCircle className="h-4 w-4" /> Fail
                                                        </button>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-200">Actual Result</Label>
                                                <MarkdownEditor value={formData.actual_result} onChange={(val) => handleChange('actual_result', val)} minHeight="150px" fieldContext={{ resourceType: 'testcase', fieldName: 'Actual Result', entityContext: buildTestcaseContext(formData) }} engagementId={formData.engagement_id} />
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-200">Notes</Label>
                                                <MarkdownEditor value={formData.notes} onChange={(val) => handleChange('notes', val)} minHeight="120px" fieldContext={{ resourceType: 'testcase', fieldName: 'Notes', entityContext: buildTestcaseContext(formData) }} engagementId={formData.engagement_id} />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                {/* ── Custom Fields ── */}
                                {hasCustomFields && (
                                    <TabsContent value="custom">
                                        <Card className="border-slate-800 bg-slate-900/50">
                                            <CardContent className="pt-6">
                                                <CustomFieldsForm
                                                    entity="testcase"
                                                    value={formData.custom_fields}
                                                    onChange={(cf) => { setFormData(prev => ({ ...prev, custom_fields: cf })); setIsDirty(true); }}
                                                    engagementId={formData.engagement_id}
                                                    hideHeading
                                                />
                                            </CardContent>
                                        </Card>
                                    </TabsContent>
                                )}
                            </div>
                        </Tabs>
                    </div>

                    {/* Sidebar with Tags */}
                    <div className="space-y-6 lg:sticky lg:top-6 self-start lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto custom-scrollbar">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
                            <div className="h-1.5 bg-linear-to-r from-purple-500 via-pink-500 to-amber-500" />
                            <CardHeader className="pb-4">
                                <CardTitle className="text-sm font-bold text-slate-200 tracking-wider uppercase">Tags</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">Select Tags</Label>
                                    <Badge variant="outline" className="text-[10px] px-1.5 h-4 border-slate-800 text-slate-500">{formData.tag_ids.length} selected</Badge>
                                </div>
                                <div className="grid grid-cols-1 gap-1.5 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                                    {isLoadingTags ? (
                                        <div className="py-4 text-center"><Loader2 className="h-4 w-4 animate-spin mx-auto text-slate-600" /></div>
                                    ) : tags.length === 0 ? (
                                        <p className="text-xs text-slate-500 text-center py-4">No tags created yet.</p>
                                    ) : (
                                        tags.map(tag => (
                                            <div
                                                key={tag.id}
                                                onClick={() => toggleTag(tag.id)}
                                                className={cn(
                                                    "flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition-all",
                                                    formData.tag_ids.includes(tag.id)
                                                        ? "bg-slate-800/40 border-slate-700 shadow-xs"
                                                        : "bg-slate-950/20 border-transparent hover:bg-slate-900/40"
                                                )}
                                            >
                                                <div
                                                    className="w-2 h-2 rounded-full shrink-0"
                                                    style={{ backgroundColor: tag.color ?? undefined }}
                                                />
                                                <span className={cn(
                                                    "text-xs font-medium truncate flex-1",
                                                    formData.tag_ids.includes(tag.id) ? "text-white" : "text-slate-400"
                                                )}>
                                                    {tag.name}
                                                </span>
                                                {formData.tag_ids.includes(tag.id) && (
                                                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                                                )}
                                            </div>
                                        ))
                                    )}
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
                            <div className="h-1.5 bg-linear-to-r from-violet-500 via-purple-500 to-fuchsia-500" />
                            <CardHeader className="pb-4">
                                <CardTitle className="text-sm font-bold text-slate-200 tracking-wider uppercase">ATT&amp;CK Techniques</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <TechniquePicker
                                    value={formData.attack_technique_ids}
                                    onChange={(ids) => handleChange('attack_technique_ids', ids)}
                                />
                            </CardContent>
                        </Card>

                        {markingProfile && (
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
                            <div className="h-1.5 bg-linear-to-r from-red-500 via-rose-500 to-orange-500" />
                            <CardHeader className="pb-4">
                                <CardTitle className="text-sm font-bold text-slate-200 tracking-wider uppercase">Classification Marking</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <EntityClassificationField
                                    engagementId={formData.engagement_id}
                                    level={formData.classification_level || null}
                                    suffix={formData.classification_suffix || null}
                                    inheritLabel="Inherit (engagement default)"
                                    label=""
                                    onChange={(lvl, suf) => {
                                        handleChange('classification_level', lvl || '');
                                        handleChange('classification_suffix', suf || '');
                                    }}
                                />
                            </CardContent>
                        </Card>
                        )}
                    </div>
                </form>
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
                            disabled={updateTestCase.isPending}
                            className={cn(
                                'gap-2 text-white',
                                hasConcurrentEditor
                                    ? 'bg-amber-600 hover:bg-amber-500'
                                    : 'bg-primary hover:bg-primary/90'
                            )}
                            title={hasConcurrentEditor ? 'Another user is editing — saving will overwrite their work' : undefined}
                        >
                            {updateTestCase.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                            {hasConcurrentEditor ? 'Save anyway' : 'Save Changes'}
                        </Button>
                    </div>
                </div>
            </div>
          </div>
          <ConfirmDialog />
        </DashboardLayout>
    );
}
