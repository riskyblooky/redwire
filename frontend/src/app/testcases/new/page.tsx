/**
 * testcases/new/page.tsx — Create Test Case Page
 *
 * Two-column form for defining a new security test case:
 *  - Main column: engagement selector (lockable via ?engagementId),
 *    title, category dropdown (11 categories from Reconnaissance to
 *    Physical), description, execution steps, and expected result
 *    (all Markdown editors with AI field context).
 *  - Sidebar: tag multi-select grid with colour indicators.
 *
 * Supports sub-test cases via ?parentId query param (displays parent
 * name). Templates can be applied via TemplatePickerDialog to pre-fill
 * title, category, description, steps, and expected result.
 */
'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
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
import { ArrowLeft, Save, Loader2, Plus, CornerDownRight, ChevronsUpDown, BookOpen, CheckCircle2 } from 'lucide-react';
import { useCreateTestCase, useTestCases } from '@/lib/hooks/use-testcases';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useTestCaseTemplates } from '@/lib/hooks/use-testcase-templates';
import { Checkbox } from '@/components/ui/checkbox';
import { useTags } from '@/lib/hooks/use-tags';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { apiErrorMessage } from '@/lib/api';

const categories = [
    { value: 'RECONNAISSANCE', label: 'Reconnaissance' },
    { value: 'SCANNING', label: 'Scanning' },
    { value: 'EXPLOITATION', label: 'Exploitation' },
    { value: 'POST_EXPLOITATION', label: 'Post Exploitation' },
    { value: 'PRIVILEGE_ESCALATION', label: 'Privilege Escalation' },
    { value: 'PERSISTENCE', label: 'Persistence' },
    { value: 'LATERAL_MOVEMENT', label: 'Lateral Movement' },
    { value: 'WEB_APPLICATION', label: 'Web Application' },
    { value: 'SOCIAL_ENGINEERING', label: 'Social Engineering' },
    { value: 'PHYSICAL', label: 'Physical' },
    { value: 'OTHER', label: 'Other' },
];

export default function NewTestCasePage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const engagementIdParam = searchParams.get('engagementId');
    const parentIdParam = searchParams.get('parentId');

    const createTestCase = useCreateTestCase();
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const { data: templates = [], isLoading: isLoadingTemplates } = useTestCaseTemplates();
    const { data: tags = [], isLoading: isLoadingTags } = useTags();
    const { data: allTestCases = [] } = useTestCases(engagementIdParam || undefined);
    const [templateOpen, setTemplateOpen] = useState(false);

    // Find parent test case name for display
    const parentTestCase = parentIdParam ? allTestCases.find(tc => tc.id === parentIdParam) : null;

    const [formData, setFormData] = useState({
        title: '',
        engagement_id: engagementIdParam || '',
        parent_id: parentIdParam || '',
        category: 'EXPLOITATION',
        description: '',
        steps: '',
        expected_result: '',
        notes: '',
        tag_ids: [] as string[],
        attack_technique_ids: [] as string[],
    });

    const handleChange = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const applyTemplate = (templateId: string) => {
        const template = templates.find(t => t.id === templateId);
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
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!formData.engagement_id) {
            toast.error('Please select an engagement');
            return;
        }

        try {
            const submitData = {
                ...formData,
                parent_id: formData.parent_id || null,
                tag_ids: formData.tag_ids || [],
                attack_technique_ids: formData.attack_technique_ids || [],
            };
            const newTC = await createTestCase.mutateAsync(submitData);
            router.push(`/testcases/${newTC.id}?engagementId=${formData.engagement_id}&tab=testcases`);
        } catch (error: any) {
            console.error('Failed to create test case:', error);
            toast.error(apiErrorMessage(error, 'Failed to create test case'));
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 w-full">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => {
                        const backPath = engagementIdParam
                            ? `/engagements/${engagementIdParam}?tab=testcases`
                            : '/testcases';
                        router.push(backPath);
                    }} className="text-slate-400 hover:text-white">
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-3xl font-bold text-white">
                            {parentTestCase ? 'New Sub-Test Case' : 'New Test Case'}
                        </h1>
                        <p className="text-slate-400 mt-1">
                            {parentTestCase ? (
                                <span className="flex items-center gap-1.5">
                                    <CornerDownRight className="h-3.5 w-3.5" />
                                    Under: <span className="text-primary font-medium">{parentTestCase.title}</span>
                                </span>
                            ) : (
                                'Define a security test to be performed'
                            )}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <Button
                        variant="outline"
                        onClick={() => setTemplateOpen(true)}
                        className="bg-slate-900/50 border-slate-800 text-slate-300 hover:bg-slate-800 hover:text-white"
                    >
                        <BookOpen className="h-4 w-4 mr-2" />
                        Use Template...
                    </Button>
                    <TemplatePickerDialog
                        open={templateOpen}
                        onOpenChange={setTemplateOpen}
                        templates={templates}
                        isLoading={isLoadingTemplates}
                        onSelect={applyTemplate}
                        title="Select Test Case Template"
                        description="Search and select a template to populate test case fields."
                    />
                </div>

                <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-4">
                    <div className="lg:col-span-3">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <CardTitle className="text-white">Definition</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="space-y-2">
                                    <Label htmlFor="engagement_id" className="text-slate-200">Engagement *</Label>
                                    <Select
                                        value={formData.engagement_id}
                                        onValueChange={(val) => handleChange('engagement_id', val)}
                                        disabled={!!engagementIdParam}
                                    >
                                        <SelectTrigger id="engagement_id" className="bg-slate-800/50 border-slate-700 text-white">
                                            <SelectValue placeholder="Select an engagement..." />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {isLoadingEngagements ? (
                                                <div className="p-2 flex justify-center"><Loader2 className="h-4 w-4 animate-spin" /></div>
                                            ) : (
                                                engagements.map((eng) => (
                                                    <SelectItem key={eng.id} value={eng.id}>{eng.name}</SelectItem>
                                                ))
                                            )}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="title" className="text-slate-200">Title *</Label>
                                    <Input
                                        id="title"
                                        value={formData.title}
                                        onChange={(e) => handleChange('title', e.target.value)}
                                        placeholder="e.g., SQL Injection on Login Page"
                                        required
                                        className="bg-slate-800/50 border-slate-700 text-white"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="category" className="text-slate-200">Category *</Label>
                                    <Select value={formData.category} onValueChange={(val) => handleChange('category', val)}>
                                        <SelectTrigger id="category" className="bg-slate-800/50 border-slate-700 text-white">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {categories.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-4">
                                    <Label htmlFor="description" className="text-slate-200">Description *</Label>
                                    <MarkdownEditor
                                        value={formData.description}
                                        onChange={(val) => handleChange('description', val)}
                                        placeholder="Goal of this test case..."
                                        minHeight="250px"
                                        fieldContext={{ resourceType: 'testcase', fieldName: 'Description' }} engagementId={formData.engagement_id}
                                    />
                                </div>

                                <div className="space-y-4">
                                    <Label htmlFor="steps" className="text-slate-200">Execution Steps</Label>
                                    <MarkdownEditor
                                        value={formData.steps}
                                        onChange={(val) => handleChange('steps', val)}
                                        placeholder="1. Navigate to /login\n2. Enter ' OR 1=1 -- in the username field..."
                                        minHeight="350px"
                                        fieldContext={{ resourceType: 'testcase', fieldName: 'Execution Steps' }} engagementId={formData.engagement_id}
                                    />
                                </div>

                                <div className="space-y-4">
                                    <Label htmlFor="expected_result" className="text-slate-200">Expected Result</Label>
                                    <MarkdownEditor
                                        value={formData.expected_result}
                                        onChange={(val) => handleChange('expected_result', val)}
                                        placeholder="The application should reject the input..."
                                        minHeight="200px"
                                        fieldContext={{ resourceType: 'testcase', fieldName: 'Expected Result' }} engagementId={formData.engagement_id}
                                    />
                                </div>

                                <div className="flex justify-end gap-3 pt-4">
                                    <Button type="button" variant="outline" onClick={() => {
                                        const backPath = engagementIdParam
                                            ? `/engagements/${engagementIdParam}?tab=testcases`
                                            : '/testcases';
                                        router.push(backPath);
                                    }} className="border-slate-700 text-slate-300">
                                        Cancel
                                    </Button>
                                    <Button type="submit" disabled={createTestCase.isPending} className="bg-primary hover:bg-primary/90 text-white">
                                        {createTestCase.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                                        Create Test Case
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Sidebar with Tags */}
                    <div className="space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md sticky top-6 overflow-hidden">
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
                    </div>
                </form>
            </div>
        </DashboardLayout>
    );
}
