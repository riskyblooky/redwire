/**
 * findings/new/page.tsx — Create Finding Page
 *
 * Tabbed form for documenting a new security vulnerability:
 *  - Overview tab: title, category (from configurable types), description
 *    and impact (Markdown editors with AI field context).
 *  - Technical tab: steps to reproduce, technical details / payloads.
 *  - Remediation tab: mitigations, external references.
 *  - Assets tab: searchable grid of engagement assets with per-asset
 *    port selection toggles.
 *
 * Sidebar: severity picker, status, CVSS 3.1 score + calculator modal,
 * engagement selector (lockable via ?engagementId query param), and
 * tag multi-select. Supports pre-filling from finding templates via
 * TemplatePickerDialog and auto-linking a test case via ?testCaseId.
 */
'use client';
import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Checkbox } from '@/components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
import {
    ArrowLeft, Save, Loader2, Bug, Target, FileText,
    Terminal, Shield, Layers, Plus, BookOpen, CheckCircle2, ChevronsUpDown, Search,
    Calculator
} from 'lucide-react';
import { useCreateFinding, useFindingTemplates, useTags } from '@/lib/hooks/use-findings';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useAssets } from '@/lib/hooks/use-assets';
import { cn } from '@/lib/utils';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { CvssCalculatorModal } from '@/components/findings/cvss-calculator-modal';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { CustomFieldsForm } from '@/components/custom-fields/custom-fields-form';
import { severityRating } from '@/lib/cvss31';
import { apiErrorMessage } from '@/lib/api';

const severities = [
    { value: 'CRITICAL', label: 'Critical', color: 'text-red-500 bg-red-500/10 border-red-500/20' },
    { value: 'HIGH', label: 'High', color: 'text-orange-500 bg-orange-500/10 border-orange-500/20' },
    { value: 'MEDIUM', label: 'Medium', color: 'text-amber-500 bg-amber-500/10 border-amber-500/20' },
    { value: 'LOW', label: 'Low', color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
    { value: 'INFO', label: 'Info', color: 'text-slate-400 bg-slate-500/10 border-slate-500/20' },
];

const statuses = [
    { value: 'OPEN', label: 'Open' },
    { value: 'IN_REVIEW', label: 'In Review' },
    { value: 'VERIFIED', label: 'Verified' },
    { value: 'REMEDIATED', label: 'Remediated' },
    { value: 'CLOSED', label: 'Closed' },
];

export default function NewFindingPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const engagementIdParam = searchParams?.get('engagementId');
    const testCaseIdParam = searchParams?.get('testCaseId');

    const createFinding = useCreateFinding();
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const { data: templates = [], isLoading: isLoadingTemplates } = useFindingTemplates();
    const { data: tags = [], isLoading: isLoadingTags } = useTags();
    const { data: findingCategories = [] } = useConfigurableTypes('finding');
    const { data: assetTypes = [] } = useConfigurableTypes('asset');

    const [formData, setFormData] = useState({
        title: '',
        engagement_id: engagementIdParam || '',
        category: '',
        severity: 'MEDIUM',
        status: 'OPEN',
        description: '',
        impact: '',
        technical_details: '',
        steps_to_reproduce: '',
        mitigations: '',
        references: '',
        cvss_score: 5.0,
        cvss_vector: '',
        asset_ids: [] as string[],
        tag_ids: [] as string[],
        attack_technique_ids: [] as string[],
        custom_fields: {} as Record<string, unknown>,
    });

    const { data: assets = [], isLoading: isLoadingAssets } = useAssets(formData.engagement_id);
    const [templateOpen, setTemplateOpen] = useState(false);
    const [cvssCalcOpen, setCvssCalcOpen] = useState(false);
    const [selectedPortIds, setSelectedPortIds] = useState<Map<string, Set<string>>>(new Map());
    const [assetSearch, setAssetSearch] = useState('');

    const filteredAssets = (() => {
        if (!assetSearch.trim()) {
            return [...assets].sort((a, b) => {
                const aS = formData.asset_ids.includes(a.id) ? 0 : 1;
                const bS = formData.asset_ids.includes(b.id) ? 0 : 1;
                return aS - bS;
            });
        }
        const q = assetSearch.toLowerCase();
        const scoreAsset = (asset: any): number => {
            const name = (asset.name || '').toLowerCase();
            const ident = (asset.identifier || '').toLowerCase();
            const type = (asset.asset_type || '').replace(/_/g, ' ').toLowerCase();
            let best = 0;
            for (const field of [name, ident]) {
                if (field === q) best = Math.max(best, 100);       // exact
                else if (field.startsWith(q)) best = Math.max(best, 75); // starts-with
                else if (field.includes(q)) best = Math.max(best, 50);   // contains
            }
            if (type === q) best = Math.max(best, 60);
            else if (type.includes(q)) best = Math.max(best, 30);
            return best;
        };
        return assets
            .map(asset => ({ asset, score: scoreAsset(asset) }))
            .filter(({ score }) => score > 0)
            .sort((a, b) => {
                const aS = formData.asset_ids.includes(a.asset.id) ? 0 : 1;
                const bS = formData.asset_ids.includes(b.asset.id) ? 0 : 1;
                if (aS !== bS) return aS - bS;
                return b.score - a.score;
            })
            .map(({ asset }) => asset);
    })();

    const handleChange = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const toggleAsset = (assetId: string) => {
        setFormData(prev => {
            const current = [...prev.asset_ids];
            const index = current.indexOf(assetId);
            if (index > -1) {
                current.splice(index, 1);
                // Clear port selections when deselecting asset
                setSelectedPortIds(prev => {
                    const next = new Map(prev);
                    next.delete(assetId);
                    return next;
                });
            } else {
                current.push(assetId);
            }
            return { ...prev, asset_ids: current };
        });
    };

    const togglePort = (assetId: string, portId: string) => {
        setSelectedPortIds(prev => {
            const next = new Map(prev);
            const portSet = new Set(next.get(assetId) || []);
            if (portSet.has(portId)) {
                portSet.delete(portId);
            } else {
                portSet.add(portId);
            }
            next.set(assetId, portSet);
            return next;
        });
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

    const applyTemplate = (templateId: string) => {
        const template = templates.find(t => t.id === templateId);
        if (template) {
            setFormData(prev => ({
                ...prev,
                title: template.title,
                category: template.category || '',
                description: template.description,
                impact: template.impact || '',
                mitigations: template.mitigations || '',
                references: template.references || prev.references,
                attack_technique_ids: (template.attack_technique_ids?.length ?? 0) > 0
                    ? template.attack_technique_ids
                    : prev.attack_technique_ids,
            }));
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!formData.engagement_id) {
            toast.error('Please select an engagement');
            return;
        }

        const score = parseFloat(formData.cvss_score.toString());

        // Strictly pick fields that exist in the Backend FindingCreate schema
        // Build asset_port_ids map from selected ports
        const assetPortIds: Record<string, string[]> = {};
        selectedPortIds.forEach((portSet, assetId) => {
            if (portSet.size > 0) {
                assetPortIds[assetId] = [...portSet];
            }
        });

        const payload = {
            engagement_id: formData.engagement_id,
            title: formData.title,
            category: formData.category || undefined,
            severity: formData.severity,
            description: formData.description,
            impact: formData.impact || undefined,
            technical_details: formData.technical_details || undefined,
            steps_to_reproduce: formData.steps_to_reproduce || undefined,
            mitigations: formData.mitigations || undefined,
            references: formData.references || undefined,
            cvss_score: isNaN(score) ? 0 : score,
            cvss_vector: formData.cvss_vector || undefined,
            asset_ids: formData.asset_ids || [],
            asset_port_ids: Object.keys(assetPortIds).length > 0 ? assetPortIds : undefined,
            tag_ids: formData.tag_ids || [],
            attack_technique_ids: formData.attack_technique_ids || [],
            testcase_id: testCaseIdParam || undefined,
            custom_fields: formData.custom_fields,
        };

        try {
            const newFinding = await createFinding.mutateAsync(payload);
            router.push(`/findings/${newFinding.id}?engagementId=${formData.engagement_id}&tab=findings`);
        } catch (error: any) {
            console.error('Failed to create finding:', error);
            const message = apiErrorMessage(error, 'Verification failed. Ensure all fields are valid.');
            toast.error(`Creation Failed: ${message}`);
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 w-full">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="icon" onClick={() => {
                            const backPath = engagementIdParam
                                ? `/engagements/${engagementIdParam}?tab=findings`
                                : '/findings';
                            router.push(backPath);
                        }} className="text-slate-400 hover:text-white">
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-3xl font-bold text-white flex items-center gap-3 tracking-tight">
                                <Bug className="h-8 w-8 text-red-500 animate-pulse" />
                                New Finding
                            </h1>
                            <p className="text-slate-400 mt-1">Document a security vulnerability discovery</p>
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
                            title="Select Finding Template"
                            description="Search and select a template to populate finding fields."
                        />

                        <Button
                            onClick={handleSubmit}
                            disabled={createFinding.isPending}
                            className="bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-900/20 px-6"
                        >
                            {createFinding.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                            Create Finding
                        </Button>
                    </div>
                </div>

                <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-4">
                    <div className="lg:col-span-3 space-y-6">
                        <Tabs defaultValue="overview" className="w-full">
                            <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1 w-full flex justify-start gap-1 rounded-xl h-12">
                                <TabsTrigger value="overview" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-red-500/10 data-[state=active]:text-red-400 transition-all font-semibold">
                                    <FileText className="h-4 w-4" />
                                    Overview
                                </TabsTrigger>
                                <TabsTrigger value="technical" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-blue-500/10 data-[state=active]:text-blue-400 transition-all font-semibold">
                                    <Terminal className="h-4 w-4" />
                                    Technical Details
                                </TabsTrigger>
                                <TabsTrigger value="remediation" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-green-500/10 data-[state=active]:text-green-400 transition-all font-semibold">
                                    <Shield className="h-4 w-4" />
                                    Remediation
                                </TabsTrigger>
                                <TabsTrigger value="assets" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-primary/10 data-[state=active]:text-primary transition-all font-semibold relative">
                                    <Target className="h-4 w-4" />
                                    Assets
                                    {formData.asset_ids.length > 0 && (
                                        <span className="absolute -top-1 -right-1 bg-primary text-white text-[10px] w-4 h-4 rounded-full flex items-center justify-center font-bold">
                                            {formData.asset_ids.length}
                                        </span>
                                    )}
                                </TabsTrigger>
                            </TabsList>

                            <div className="mt-6">
                                <TabsContent value="overview">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6 space-y-6">
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="space-y-2">
                                                    <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Title *</Label>
                                                    <Input
                                                        value={formData.title}
                                                        onChange={(e) => handleChange('title', e.target.value)}
                                                        placeholder="Vulnerability title..."
                                                        required
                                                        className="bg-slate-950/50 border-slate-800 text-white h-11 focus:ring-red-500/30"
                                                    />
                                                </div>
                                                <div className="space-y-2">
                                                    <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Category</Label>
                                                    <Select value={formData.category} onValueChange={(value) => handleChange('category', value)}>
                                                        <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-11">
                                                            <SelectValue placeholder="Select category..." />
                                                        </SelectTrigger>
                                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                            {findingCategories.map((type) => (
                                                                <SelectItem key={type.id} value={type.name}>
                                                                    {type.name}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Description *</Label>
                                                <MarkdownEditor
                                                    value={formData.description}
                                                    onChange={(val) => handleChange('description', val)}
                                                    placeholder="Detailed description of the vulnerability..."
                                                    minHeight="400px"
                                                    fieldContext={{ resourceType: 'finding', fieldName: 'Description' }} engagementId={formData.engagement_id}
                                                />
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Impact</Label>
                                                <MarkdownEditor
                                                    value={formData.impact}
                                                    onChange={(val) => handleChange('impact', val)}
                                                    placeholder="Business or technical impact..."
                                                    minHeight="300px"
                                                    fieldContext={{ resourceType: 'finding', fieldName: 'Impact' }} engagementId={formData.engagement_id}
                                                />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="technical">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6 space-y-6">
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Steps to Reproduce</Label>
                                                <MarkdownEditor
                                                    value={formData.steps_to_reproduce}
                                                    onChange={(val) => handleChange('steps_to_reproduce', val)}
                                                    placeholder="1. Navigate to...&#10;2. Input payload...&#10;3. Observe response..."
                                                    minHeight="300px"
                                                    fieldContext={{ resourceType: 'finding', fieldName: 'Steps to Reproduce' }} engagementId={formData.engagement_id}
                                                />
                                            </div>

                                            <div className="space-y-4">
                                                <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Technical Details</Label>
                                                <MarkdownEditor
                                                    value={formData.technical_details}
                                                    onChange={(val) => handleChange('technical_details', val)}
                                                    placeholder="Detailed proof-of-concept, payload examples, or code snippets..."
                                                    minHeight="300px"
                                                    fieldContext={{ resourceType: 'finding', fieldName: 'Technical Details' }} engagementId={formData.engagement_id}
                                                />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="remediation">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6 space-y-6">
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">Mitigations</Label>
                                                <MarkdownEditor
                                                    value={formData.mitigations}
                                                    onChange={(val) => handleChange('mitigations', val)}
                                                    placeholder="Recommended fix or patching steps..."
                                                    minHeight="250px"
                                                    fieldContext={{ resourceType: 'finding', fieldName: 'Mitigations' }} engagementId={formData.engagement_id}
                                                />
                                            </div>
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 font-medium tracking-wide uppercase text-[10px]">References</Label>
                                                <MarkdownEditor
                                                    value={formData.references}
                                                    onChange={(val) => handleChange('references', val)}
                                                    placeholder="CVE links, blog posts, advisories..."
                                                    minHeight="200px"
                                                    fieldContext={{ resourceType: 'finding', fieldName: 'References' }} engagementId={formData.engagement_id}
                                                />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="assets">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardHeader>
                                            <CardTitle className="text-white text-lg">Affected Assets</CardTitle>
                                            <CardDescription className="text-slate-400">Select which assets from the engagement are affected by this finding.</CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                            {isLoadingAssets ? (
                                                <div className="flex flex-col items-center justify-center py-12">
                                                    <Loader2 className="h-8 w-8 animate-spin text-primary mb-2" />
                                                    <p className="text-slate-500 text-sm">Loading engagement assets...</p>
                                                </div>
                                            ) : assets.length === 0 ? (
                                                <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                                                    <Target className="h-12 w-12 mx-auto mb-4 text-slate-700" />
                                                    <p className="text-slate-400 font-medium">No assets found for this engagement</p>
                                                    <p className="text-slate-500 text-xs mt-1">Visit the Assets tab to add some first.</p>
                                                </div>
                                            ) : (
                                                <>
                                                    <div className="mb-4 relative">
                                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                                        <Input
                                                            value={assetSearch}
                                                            onChange={(e) => setAssetSearch(e.target.value)}
                                                            placeholder="Search assets by name, IP, hostname, type..."
                                                            className="pl-10 bg-slate-950/50 border-slate-800 text-white h-10 focus:ring-primary/30"
                                                        />
                                                        {assetSearch && (
                                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-500">
                                                                {filteredAssets.length} of {assets.length}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <ScrollArea className="h-[400px] pr-4">
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                            {filteredAssets.map((asset) => (
                                                                <div key={asset.id} className="space-y-1">
                                                                    <div
                                                                        className={cn(
                                                                            "flex items-center space-x-3 p-3 rounded-lg border cursor-pointer",
                                                                            formData.asset_ids.includes(asset.id)
                                                                                ? "bg-primary/10 border-primary/40 shadow-[0_0_15px_rgba(168,85,247,0.1)]"
                                                                                : "bg-slate-950/30 border-slate-800 hover:border-slate-700"
                                                                        )}
                                                                    >
                                                                        <Checkbox
                                                                            id={`asset-${asset.id}`}
                                                                            checked={formData.asset_ids.includes(asset.id)}
                                                                            onCheckedChange={() => toggleAsset(asset.id)}
                                                                            className="border-slate-700 data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                                                                        />
                                                                        <Label
                                                                            htmlFor={`asset-${asset.id}`}
                                                                            className="flex flex-1 items-center justify-between cursor-pointer min-w-0"
                                                                        >
                                                                            <div className="flex flex-col min-w-0 pr-2">
                                                                                <span className="text-sm font-bold text-white truncate">{asset.name}</span>
                                                                                <span className="text-[10px] text-slate-500 font-mono truncate uppercase tracking-tighter mt-0.5">{asset.identifier}</span>
                                                                            </div>
                                                                            {(() => {
                                                                                const normalized = asset.asset_type?.replace(/_/g, ' ').toLowerCase();
                                                                                const typeConfig = assetTypes.find(t => t.name.toLowerCase() === normalized);
                                                                                const color = typeConfig?.color || '#64748b';
                                                                                const r = parseInt(color.slice(1, 3), 16);
                                                                                const g = parseInt(color.slice(3, 5), 16);
                                                                                const b = parseInt(color.slice(5, 7), 16);
                                                                                return (
                                                                                    <Badge className="text-[9px] px-1.5 py-0 h-4 border-none uppercase font-bold shrink-0"
                                                                                        style={{ backgroundColor: `rgba(${r},${g},${b},0.15)`, color: color }}
                                                                                    >
                                                                                        {asset.asset_type?.replace(/_/g, ' ')}
                                                                                    </Badge>
                                                                                );
                                                                            })()}
                                                                        </Label>
                                                                    </div>
                                                                    {/* Port selection for selected assets */}
                                                                    {formData.asset_ids.includes(asset.id) && asset.ports && asset.ports.length > 0 && (
                                                                        <div className="ml-8 p-2 bg-slate-950/30 rounded-lg border border-slate-800/40 space-y-1">
                                                                            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Select Ports</span>
                                                                            <div className="flex flex-wrap gap-1.5">
                                                                                {asset.ports.map((port) => {
                                                                                    const isSelected = selectedPortIds.get(asset.id)?.has(port.id) || false;
                                                                                    return (
                                                                                        <button
                                                                                            key={port.id}
                                                                                            type="button"
                                                                                            onClick={() => togglePort(asset.id, port.id)}
                                                                                            className={cn(
                                                                                                "text-[9px] px-2 py-0.5 rounded font-mono font-bold border transition-all",
                                                                                                isSelected
                                                                                                    ? port.state === 'OPEN' ? 'bg-green-500/20 border-green-500/40 text-green-400'
                                                                                                        : port.state === 'FILTERED' ? 'bg-yellow-500/20 border-yellow-500/40 text-yellow-400'
                                                                                                            : 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400'
                                                                                                    : 'bg-slate-900/40 border-slate-700/40 text-slate-500 hover:border-slate-600'
                                                                                            )}
                                                                                        >
                                                                                            {port.port_number}/{port.protocol}
                                                                                            {port.service_name && ` (${port.service_name})`}
                                                                                        </button>
                                                                                    );
                                                                                })}
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ))}

                                                        </div>
                                                    </ScrollArea>
                                                </>
                                            )}
                                        </CardContent>
                                    </Card>
                                </TabsContent>
                            </div>
                        </Tabs>
                    </div>

                    {/* Sidebar */}
                    <div className="space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md sticky top-6 overflow-hidden">
                            <div className="h-1.5 bg-linear-to-r from-red-500 via-orange-500 to-amber-500" />
                            <CardHeader className="pb-4">
                                <CardTitle className="text-sm font-bold text-slate-200 tracking-wider uppercase">Classification</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">Severity</Label>
                                    <Select value={formData.severity} onValueChange={(val) => handleChange('severity', val)}>
                                        <SelectTrigger className={cn("bg-slate-950/50 border-slate-800 text-white font-bold h-11", severities.find(s => s.value === formData.severity)?.color)}>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {severities.map((s) => (
                                                <SelectItem key={s.value} value={s.value} className={cn("font-bold my-1 mx-1 rounded-md", s.color)}>
                                                    {s.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">Status</Label>
                                    <Select value={formData.status} onValueChange={(val) => handleChange('status', val)}>
                                        <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-11">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {statuses.map((s) => (
                                                <SelectItem key={s.value} value={s.value}>
                                                    {s.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-3 pt-2">
                                    <div className="flex items-center justify-between mb-2">
                                        <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">CVSS v3.1</Label>
                                        <div className="flex items-center gap-2">
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                onClick={() => setCvssCalcOpen(true)}
                                                className="h-5 px-2 text-[10px] border-slate-700 text-amber-500 hover:text-amber-400 hover:bg-amber-500/10 gap-1"
                                            >
                                                <Calculator className="h-3 w-3" />
                                                Calc
                                            </Button>
                                            <Badge variant="secondary" className="bg-slate-800 text-white border-none font-mono px-1.5 py-0 h-5">
                                                {formData.cvss_score}
                                            </Badge>
                                        </div>
                                    </div>
                                    <Input
                                        type="number"
                                        step="0.1"
                                        min="0"
                                        max="10"
                                        value={formData.cvss_score}
                                        onChange={(e) => handleChange('cvss_score', e.target.value)}
                                        className="bg-slate-950/50 border-slate-800 text-white h-11 text-center font-bold font-mono text-lg"
                                    />
                                    <Input
                                        value={formData.cvss_vector}
                                        onChange={(e) => handleChange('cvss_vector', e.target.value)}
                                        placeholder="CVSS:3.1/AV:N/AC:L..."
                                        className="bg-slate-950/50 border-slate-800 text-white font-mono text-[10px] h-9 focus:ring-amber-500/30"
                                    />
                                </div>

                                <CvssCalculatorModal
                                    open={cvssCalcOpen}
                                    onOpenChange={setCvssCalcOpen}
                                    initialVector={formData.cvss_vector}
                                    onApply={(score, vector) => {
                                        handleChange('cvss_score', score);
                                        handleChange('cvss_vector', vector);
                                        const sev = severityRating(score);
                                        const sevMap: Record<string, string> = { Critical: 'CRITICAL', High: 'HIGH', Medium: 'MEDIUM', Low: 'LOW', None: 'INFO' };
                                        handleChange('severity', sevMap[sev] || 'MEDIUM');
                                    }}
                                />

                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">Engagement *</Label>
                                    <Select
                                        value={formData.engagement_id}
                                        onValueChange={(val) => handleChange('engagement_id', val)}
                                        disabled={!!engagementIdParam}
                                    >
                                        <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white text-xs h-11">
                                            <SelectValue placeholder="Project..." />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {isLoadingEngagements ? <div className="p-4 text-center"><Loader2 className="h-5 w-5 animate-spin mx-auto text-primary" /></div> :
                                                engagements.map((eng) => <SelectItem key={eng.id} value={eng.id}>{eng.name}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <Separator className="bg-slate-800/40" />

                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest flex items-center justify-between">
                                        Tags
                                        <Badge variant="outline" className="text-[10px] px-1.5 h-4 border-slate-800 text-slate-500">{formData.tag_ids.length} selected</Badge>
                                    </Label>
                                    <div className="grid grid-cols-1 gap-1.5 max-h-[200px] overflow-y-auto pr-2 custom-scrollbar">
                                        {isLoadingTags ? (
                                            <div className="py-4 text-center"><Loader2 className="h-4 w-4 animate-spin mx-auto text-slate-600" /></div>
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
                                </div>

                                <Separator className="bg-slate-800/40" />

                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">ATT&CK Techniques</Label>
                                    <TechniquePicker
                                        value={formData.attack_technique_ids}
                                        onChange={(ids) => handleChange('attack_technique_ids', ids)}
                                    />
                                </div>
                            </CardContent>
                        </Card>

                        <CustomFieldsForm
                            entity="finding"
                            value={formData.custom_fields}
                            onChange={(cf) => setFormData(prev => ({ ...prev, custom_fields: cf }))}
                        />
                    </div>
                </form>
            </div>
        </DashboardLayout>
    );
}

