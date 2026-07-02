/**
 * templates/testcases/[id]/edit/page.tsx — Test Case Template Editor
 *
 * Create / edit form for test-case templates. Fields: title, category
 * (select from `TEST_CASE_CATEGORIES`), description (MarkdownEditor),
 * steps (MarkdownEditor), expected result (MarkdownEditor).
 *
 * Route `[id]=new` enters create mode; any other ID loads the existing
 * template for editing. Permission-gated to ADMIN / TEAM_LEAD.
 * Redirects to `/templates?tab=testcases` on save.
 */
'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import {
    useTestCaseTemplate,
    useCreateTestCaseTemplate,
    useUpdateTestCaseTemplate,
} from '@/lib/hooks/use-testcase-templates';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { MarkdownEditor } from '@/components/ui/markdown-editor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { apiErrorMessage } from '@/lib/api';
import {
    ArrowLeft,
    Save,
    Loader2,
    ClipboardList,
} from 'lucide-react';

const TEST_CASE_CATEGORIES = [
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

export default function TestCaseTemplateEditPage() {
    const params = useParams();
    const router = useRouter();
    const { user } = useAuthStore();
    const isNew = params?.id === 'new';
    const templateId = isNew ? undefined : params?.id as string;

    const canManage = user?.role === UserRole.ADMIN || user?.role === UserRole.TEAM_LEAD;

    const { data: template, isLoading } = useTestCaseTemplate(templateId);
    const createTemplate = useCreateTestCaseTemplate();
    const updateTemplate = useUpdateTestCaseTemplate();

    const isOwner = !!template && template.created_by === user?.id;
    const isDraft = template?.status === 'DRAFT';
    const isSubmitted = template?.status === 'SUBMITTED';
    const isPublished = template?.status === 'PUBLISHED';
    const allowedToEdit = isNew
        || (isDraft && (isOwner || canManage))
        || (isPublished && canManage);

    const [title, setTitle] = useState('');
    const [category, setCategory] = useState('');
    const [description, setDescription] = useState('');
    const [steps, setSteps] = useState('');
    const [expectedResult, setExpectedResult] = useState('');
    const [attackTechniqueIds, setAttackTechniqueIds] = useState<string[]>([]);

    useEffect(() => {
        if (template) {
            setTitle(template.title);
            setCategory(template.category || '');
            setDescription(template.description || '');
            setSteps(template.steps || '');
            setExpectedResult(template.expected_result || '');
            setAttackTechniqueIds(template.attack_technique_ids || []);
        }
    }, [template]);

    const handleSave = async () => {
        if (!title.trim()) {
            toast.error('Title is required');
            return;
        }
        if (!category.trim()) {
            toast.error('Category is required');
            return;
        }
        if (!description.trim()) {
            toast.error('Description is required');
            return;
        }

        const data = {
            title: title.trim(),
            category: category.trim(),
            description: description.trim(),
            steps: steps.trim() || undefined,
            expected_result: expectedResult.trim() || undefined,
            attack_technique_ids: attackTechniqueIds,
        };

        try {
            if (isNew) {
                await createTemplate.mutateAsync(data);
                toast.success('Test case template created');
            } else {
                await updateTemplate.mutateAsync({ id: templateId!, ...data });
                toast.success('Test case template updated');
            }
            router.push('/templates?tab=testcases');
        } catch (err: any) {
            const message = apiErrorMessage(err, `Failed to ${isNew ? 'create' : 'update'} template`);
            toast.error(message);
        }
    };

    if (!isNew && !isLoading && !allowedToEdit) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px] text-slate-400 text-center px-4">
                    {isSubmitted
                        ? "This template is locked while it's pending review. Withdraw the submission (or have a reviewer reject it) before editing."
                        : "You don't have permission to edit this template."}
                </div>
            </DashboardLayout>
        );
    }

    if (!isNew && isLoading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    const isPending = createTemplate.isPending || updateTemplate.isPending;

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 w-full max-w-5xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => router.push('/templates?tab=testcases')}
                            className="text-slate-400 hover:text-white"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                                <ClipboardList className="h-6 w-6 text-cyan-400" />
                                {isNew ? 'New Test Case Template' : 'Edit Test Case Template'}
                            </h1>
                            {!isNew && template && (
                                <p className="text-slate-400 mt-1">{template.title}</p>
                            )}
                        </div>
                    </div>
                    <Button
                        onClick={handleSave}
                        disabled={isPending}
                        className="bg-primary hover:bg-primary/90 text-white px-6"
                    >
                        {isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                        {isNew ? 'Create Template' : 'Save Changes'}
                    </Button>
                </div>

                {/* Form */}
                <div className="space-y-6">
                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-6 space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="title">Title *</Label>
                                    <Input
                                        id="title"
                                        value={title}
                                        onChange={e => setTitle(e.target.value)}
                                        placeholder="e.g. Check for Default Credentials"
                                        className="bg-slate-800/50 border-slate-700"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Category *</Label>
                                    <Select value={category} onValueChange={setCategory}>
                                        <SelectTrigger className="bg-slate-800/50 border-slate-700">
                                            <SelectValue placeholder="Select a category" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800">
                                            {TEST_CASE_CATEGORIES.map(cat => (
                                                <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-6 space-y-2">
                            <Label>Description *</Label>
                            <MarkdownEditor
                                value={description}
                                onChange={setDescription}
                                placeholder="What this test case verifies..."
                                minHeight="200px"
                                fieldContext={{ resourceType: 'testcase template', fieldName: 'Description' }}
                            />
                        </CardContent>
                    </Card>

                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-6 space-y-2">
                            <Label>Steps</Label>
                            <MarkdownEditor
                                value={steps}
                                onChange={setSteps}
                                placeholder="Step-by-step test procedure..."
                                minHeight="200px"
                                fieldContext={{ resourceType: 'testcase template', fieldName: 'Steps' }}
                            />
                        </CardContent>
                    </Card>

                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-6 space-y-2">
                            <Label>Expected Result</Label>
                            <MarkdownEditor
                                value={expectedResult}
                                onChange={setExpectedResult}
                                placeholder="What should happen if the test passes..."
                                minHeight="150px"
                                fieldContext={{ resourceType: 'testcase template', fieldName: 'Expected Result' }}
                            />
                        </CardContent>
                    </Card>

                    <Card className="border-slate-800 bg-slate-900/50">
                        <CardContent className="p-6 space-y-2">
                            <Label>ATT&amp;CK Techniques</Label>
                            <p className="text-xs text-slate-500">
                                MITRE ATT&amp;CK techniques exercised by this test case — applied to the test case when the template is used.
                            </p>
                            <TechniquePicker
                                value={attackTechniqueIds}
                                onChange={setAttackTechniqueIds}
                            />
                        </CardContent>
                    </Card>
                </div>
            </div>
        </DashboardLayout>
    );
}
