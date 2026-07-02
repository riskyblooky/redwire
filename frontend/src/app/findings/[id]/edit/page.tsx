/**
 * findings/[id]/edit/page.tsx — Edit Finding Page
 *
 * Tabbed edit form mirroring the create page layout (Overview, Technical,
 * Remediation, Assets). Pre-populates all fields from the existing finding
 * including previously selected assets, port mappings, and tags.
 *
 * Key differences from the create page:
 *  - Template application requires a confirmation dialog (overwrites fields).
 *  - Port selections are initialised from the finding's saved port_ids.
 *  - The engagement selector is read-only (engagement cannot be changed).
 *  - Preserves ?engagementId and ?tab query params for return navigation.
 *  - CVSS calculator modal syncs score → severity automatically.
 */
'use client';

import { useParams } from '@/lib/hooks/use-params';

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
    Terminal, Shield, Layers, Plus, BookOpen, CheckCircle2, Edit, ChevronsUpDown,
    Calculator, Search
} from 'lucide-react';
import { useFinding, useUpdateFinding, useFindingTemplates, useTags } from '@/lib/hooks/use-findings';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useAssets } from '@/lib/hooks/use-assets';
import { cn } from '@/lib/utils';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { useConfirmDialog } from '@/components/ui/confirm-dialog';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { CvssCalculatorModal } from '@/components/findings/cvss-calculator-modal';
import { TechniquePicker } from '@/components/ui/technique-picker';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { PresenceIndicator } from '@/components/collaboration/presence-indicator';
import { EditLockBanner } from '@/components/collaboration/edit-lock-banner';
import { VersionHistoryPanel } from '@/components/ui/version-history-panel';
import { useAuthStore } from '@/stores/auth-store';
import { severityRating } from '@/lib/cvss31';
import { useNavigationGuard } from '@/lib/hooks/use-navigation-guard';
import { EntityClassificationField } from '@/components/marking/entity-classification-field';
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

export default function EditFindingPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = useParams(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const returnEngagementId = searchParams.get('engagementId');
    const returnTab = searchParams.get('tab') || 'findings';

    const { data: finding, isLoading: isLoadingFinding } = useFinding(id);
    const { data: engagements = [] } = useEngagements();
    const { data: templates = [], isLoading: isLoadingTemplates } = useFindingTemplates();
    const { data: tags = [], isLoading: isLoadingTags } = useTags();
    const updateFinding = useUpdateFinding();
    const { confirm, ConfirmDialog } = useConfirmDialog();

    // Live presence — same channel as the view page, so both audiences
    // appear together. mode:'edit' tags this connection as actively
    // editing so other editors can warn each other.
    const currentUserId = useAuthStore(s => s.user?.id);
    const { activeUsers } = useCollaboration({
        resourceType: 'finding',
        resourceId: id,
        enabled: !!finding,
        mode: 'edit',
    });
    const otherEditors = activeUsers.filter(
        u => u.mode === 'edit' && u.id !== currentUserId
    );
    const hasConcurrentEditor = otherEditors.length > 0;
    const { data: findingCategories = [] } = useConfigurableTypes('finding');
    const { data: assetTypes = [] } = useConfigurableTypes('asset');
    const [templateOpen, setTemplateOpen] = useState(false);
    const [cvssCalcOpen, setCvssCalcOpen] = useState(false);
    const [isDirty, setIsDirty] = useState(false);

    const getBackPath = () => {
        const query = returnEngagementId ? `?engagementId=${returnEngagementId}&tab=${returnTab}` : '';
        return `/findings/${id}${query}`;
    };

    const { navigateWithGuard } = useNavigationGuard(isDirty, confirm);

    const [formData, setFormData] = useState({
        title: '',
        engagement_id: '',
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
        classification_level: '' as string,
        classification_suffix: '' as string,
        asset_ids: [] as string[],
        tag_ids: [] as string[],
        attack_technique_ids: [] as string[],
    });

    const { data: assets = [] } = useAssets(formData.engagement_id);
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

    useEffect(() => {
        if (finding) {
            setFormData({
                title: finding.title,
                engagement_id: finding.engagement_id,
                category: finding.category || '',
                severity: finding.severity?.toUpperCase().trim(),
                status: finding.status?.toUpperCase().trim(),
                description: finding.description,
                impact: finding.impact || '',
                technical_details: finding.technical_details || '',
                steps_to_reproduce: finding.steps_to_reproduce || '',
                mitigations: finding.mitigations || '',
                references: finding.references || '',
                cvss_score: finding.cvss_score || 0,
                cvss_vector: finding.cvss_vector || '',
                classification_level: finding.classification_level || '',
                classification_suffix: finding.classification_suffix || '',
                asset_ids: finding.assets?.map((a: any) => a.id) || [],
                tag_ids: finding.tags?.map((t: any) => t.id) || [],
                attack_technique_ids: finding.attack_technique_ids || [],
            });
            // Initialize port selections from finding response
            if (finding.assets) {
                const portMap = new Map<string, Set<string>>();
                for (const asset of finding.assets as any[]) {
                    if (asset.port_ids && asset.port_ids.length > 0) {
                        portMap.set(asset.id, new Set(asset.port_ids));
                    }
                }
                if (portMap.size > 0) setSelectedPortIds(portMap);
            }
            setIsDirty(false);
        }
    }, [finding]);

    const handleChange = (field: string, value: any) => {
        setFormData(prev => ({ ...prev, [field]: value }));
        setIsDirty(true);
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
        setIsDirty(true);
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
        setIsDirty(true);
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

    const applyTemplate = async (templateId: string) => {
        const confirmed = await confirm({
            title: 'Apply Template',
            description: 'This will overwrite current fields with the selected template. Continue?',
            variant: 'warning',
            confirmLabel: 'Apply',
        });
        if (!confirmed) return;

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
                // Preserve other fields like severity/status unless you want to overwrite them too?
                // Usually templates might have a default severity but often we want to keep current context.
                // Let's assume we keep finding specific fields like assets, but overwrite content.
            }));
            setIsDirty(true);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        // Warn before verifying a finding that still has unresolved discussion threads.
        // Only fires when the user actually changes the status to VERIFIED on this save.
        const previousStatus = finding?.status?.toUpperCase().trim();
        if (
            formData.status === 'VERIFIED' &&
            previousStatus !== 'VERIFIED' &&
            (finding?.unresolved_thread_count || 0) > 0
        ) {
            const count = finding!.unresolved_thread_count!;
            const ok = await confirm({
                title: 'Verify finding with unresolved comments?',
                description: `This finding has ${count} unresolved discussion ${count === 1 ? 'thread' : 'threads'}. Marking it Verified now will leave ${count === 1 ? 'that thread' : 'those threads'} open. Continue anyway?`,
                confirmLabel: 'Verify anyway',
                variant: 'warning',
            });
            if (!ok) return;
        }

        const score = parseFloat(formData.cvss_score.toString());

        // Build asset_port_ids map from selected ports
        const assetPortIds: Record<string, string[]> = {};
        selectedPortIds.forEach((portSet, assetId) => {
            if (portSet.size > 0) {
                assetPortIds[assetId] = [...portSet];
            }
        });

        // Strictly pick fields that exist in the Backend FindingUpdate schema
        const payload = {
            title: formData.title,
            category: formData.category || undefined,
            severity: formData.severity,
            status: formData.status,
            description: formData.description,
            impact: formData.impact || undefined,
            technical_details: formData.technical_details || undefined,
            steps_to_reproduce: formData.steps_to_reproduce || undefined,
            mitigations: formData.mitigations || undefined,
            references: formData.references || undefined,
            cvss_score: isNaN(score) ? 0 : score,
            cvss_vector: formData.cvss_vector || undefined,
            classification_level: formData.classification_level || null,
            classification_suffix: formData.classification_suffix || null,
            asset_ids: formData.asset_ids || [],
            asset_port_ids: Object.keys(assetPortIds).length > 0 ? assetPortIds : undefined,
            tag_ids: formData.tag_ids || [],
            attack_technique_ids: formData.attack_technique_ids || [],
        };

        try {
            await updateFinding.mutateAsync({
                id: id,
                ...payload,
            });
            setIsDirty(false);
            const query = returnEngagementId ? `?engagementId=${returnEngagementId}&tab=${returnTab}` : '';
            router.push(`/findings/${id}${query}`);
        } catch (error: any) {
            console.error('Failed to update finding:', error);
            const detail = apiErrorMessage(error);
            const message = typeof detail === 'string' ? detail :
                Array.isArray(detail) ? detail.map((d: any) => `${d.loc.join('.')}: ${d.msg}`).join('\n') :
                    'Verification failed. Ensure all fields are valid.';
            toast.error(`Update Failed: ${message}`);
        }
    };

    if (isLoadingFinding) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-red-500" />
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
          <div className="flex flex-col min-h-full">
            {/* ── Sticky page header ── */}
            <div className="sticky top-0 z-20 bg-slate-950/90 backdrop-blur-md border-b border-slate-800/50">
                <div className="flex items-center justify-between px-6 pt-5 pb-4">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => navigateWithGuard(getBackPath())}
                            className="text-slate-400 hover:text-white hover:bg-slate-800"
                        >
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                                <Edit className="h-6 w-6 text-blue-500" /> Edit Finding
                            </h1>
                            <p className="text-slate-400 text-sm mt-0.5 truncate">{finding?.title}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 relative z-30">
                        {activeUsers.length > 0 && <PresenceIndicator users={activeUsers} />}
                        {finding && <VersionHistoryPanel entityType="finding" entityId={id} currentData={finding} />}
                        <div className="h-8 w-px bg-slate-800" />
                        <Button
                            variant="outline"
                            onClick={() => setTemplateOpen(true)}
                            className="bg-slate-900/50 border-slate-800 text-slate-300 hover:bg-slate-800 hover:text-white"
                        >
                            <BookOpen className="h-4 w-4 mr-2" />
                            Overwrite with...
                        </Button>
                    </div>
                </div>
            </div>
            <TemplatePickerDialog
                open={templateOpen}
                onOpenChange={setTemplateOpen}
                templates={templates}
                isLoading={isLoadingTemplates}
                onSelect={applyTemplate}
                title="Select Finding Template"
                description="This will overwrite current fields with the selected template."
            />

            <EditLockBanner otherEditors={otherEditors} />

            {/* Main content */}
            <div className="p-6 pb-28 flex-1">
                <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-4">
                    <div className="lg:col-span-3 space-y-6">
                        <Tabs defaultValue="technical" className="w-full">
                            <TabsList className="bg-slate-950/40 border border-slate-800/60 p-1 w-full flex justify-start gap-1 rounded-xl h-12">
                                <TabsTrigger value="overview" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-red-500/10 data-[state=active]:text-red-400 font-semibold">
                                    <FileText className="h-4 w-4" /> Overview
                                </TabsTrigger>
                                <TabsTrigger value="technical" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-blue-500/10 data-[state=active]:text-blue-400 font-semibold">
                                    <Terminal className="h-4 w-4" /> Technical
                                </TabsTrigger>
                                <TabsTrigger value="remediation" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-green-500/10 data-[state=active]:text-green-400 font-semibold">
                                    <Shield className="h-4 w-4" /> Remediation
                                </TabsTrigger>
                                <TabsTrigger value="assets" className="flex items-center gap-2 px-6 py-2 rounded-lg data-[state=active]:bg-primary/10 data-[state=active]:text-primary font-semibold">
                                    <Target className="h-4 w-4" /> Assets
                                </TabsTrigger>
                            </TabsList>

                            <div className="mt-6">
                                <TabsContent value="overview">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6 space-y-6">
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="space-y-2">
                                                    <Label className="text-slate-300 uppercase text-[10px]">Title *</Label>
                                                    <Input value={formData.title} onChange={(e) => handleChange('title', e.target.value)} required className="bg-slate-950/50 border-slate-800 text-white h-11" />
                                                </div>
                                                <div className="space-y-2">
                                                    <Label className="text-slate-300 uppercase text-[10px]">Category</Label>
                                                    <Select key={`${finding?.id}-${formData.category}`} value={formData.category} onValueChange={(value) => handleChange('category', value)}>
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
                                            <EntityClassificationField
                                                engagementId={formData.engagement_id}
                                                level={formData.classification_level || null}
                                                suffix={formData.classification_suffix || null}
                                                inheritLabel="Inherit (engagement default)"
                                                label="Classification Marking"
                                                onChange={(lvl, suf) => {
                                                    handleChange('classification_level', lvl || '');
                                                    handleChange('classification_suffix', suf || '');
                                                }}
                                            />
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 uppercase text-[10px]">Description *</Label>
                                                <MarkdownEditor value={formData.description} onChange={(val) => handleChange('description', val)} minHeight="400px" fieldContext={{ resourceType: 'finding', fieldName: 'Description' }} engagementId={formData.engagement_id} />
                                            </div>
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 uppercase text-[10px]">Impact</Label>
                                                <MarkdownEditor value={formData.impact} onChange={(val) => handleChange('impact', val)} minHeight="300px" fieldContext={{ resourceType: 'finding', fieldName: 'Impact' }} engagementId={formData.engagement_id} />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="technical">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6 space-y-6">
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 uppercase text-[10px]">Steps to Reproduce</Label>
                                                <MarkdownEditor value={formData.steps_to_reproduce} onChange={(val) => handleChange('steps_to_reproduce', val)} minHeight="300px" fieldContext={{ resourceType: 'finding', fieldName: 'Steps to Reproduce' }} engagementId={formData.engagement_id} />
                                            </div>
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 uppercase text-[10px]">Technical Details</Label>
                                                <MarkdownEditor value={formData.technical_details} onChange={(val) => handleChange('technical_details', val)} minHeight="300px" fieldContext={{ resourceType: 'finding', fieldName: 'Technical Details' }} engagementId={formData.engagement_id} />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="remediation">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6 space-y-6">
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 uppercase text-[10px]">Mitigations</Label>
                                                <MarkdownEditor value={formData.mitigations} onChange={(val) => handleChange('mitigations', val)} minHeight="250px" fieldContext={{ resourceType: 'finding', fieldName: 'Mitigations' }} engagementId={formData.engagement_id} />
                                            </div>
                                            <div className="space-y-4">
                                                <Label className="text-slate-300 uppercase text-[10px]">References</Label>
                                                <MarkdownEditor value={formData.references} onChange={(val) => handleChange('references', val)} minHeight="200px" fieldContext={{ resourceType: 'finding', fieldName: 'References' }} engagementId={formData.engagement_id} />
                                            </div>
                                        </CardContent>
                                    </Card>
                                </TabsContent>

                                <TabsContent value="assets">
                                    <Card className="border-slate-800 bg-slate-900/40 backdrop-blur-xs border-t-0 rounded-t-none">
                                        <CardContent className="pt-6">
                                            {assets.length === 0 ? (
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
                                                                            formData.asset_ids.includes(asset.id) ? "bg-primary/10 border-primary/40" : "bg-slate-950/30 border-slate-800"
                                                                        )}
                                                                    >
                                                                        <Checkbox
                                                                            id={`edit-asset-${asset.id}`}
                                                                            checked={formData.asset_ids.includes(asset.id)}
                                                                            onCheckedChange={() => toggleAsset(asset.id)}
                                                                        />
                                                                        <Label
                                                                            htmlFor={`edit-asset-${asset.id}`}
                                                                            className="flex-1 flex flex-col min-w-0 cursor-pointer"
                                                                        >
                                                                            <div className="flex items-center gap-2">
                                                                                <span className="text-sm font-bold text-white truncate">{asset.name}</span>
                                                                                {(() => {
                                                                                    const normalized = asset.asset_type?.replace(/_/g, ' ').toLowerCase();
                                                                                    const typeConfig = assetTypes.find(t => t.name.toLowerCase() === normalized);
                                                                                    const color = typeConfig?.color || '#64748b';
                                                                                    const r = parseInt(color.slice(1, 3), 16);
                                                                                    const g = parseInt(color.slice(3, 5), 16);
                                                                                    const b = parseInt(color.slice(5, 7), 16);
                                                                                    return (
                                                                                        <Badge className="text-[8px] px-1.5 py-0 h-4 border-none uppercase font-bold shrink-0"
                                                                                            style={{ backgroundColor: `rgba(${r},${g},${b},0.15)`, color: color }}
                                                                                        >
                                                                                            {asset.asset_type?.replace(/_/g, ' ')}
                                                                                        </Badge>
                                                                                    );
                                                                                })()}
                                                                            </div>
                                                                            <span className="text-[10px] text-slate-500 font-mono truncate uppercase mt-0.5">{asset.identifier}</span>
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
                    <div className="space-y-6 lg:sticky lg:top-6 self-start lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto custom-scrollbar">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
                            <div className="h-1.5 bg-linear-to-r from-blue-500 to-indigo-500" />
                            <CardHeader className="pb-4">
                                <CardTitle className="text-sm font-bold text-slate-200 tracking-wider uppercase">Classification</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">Severity</Label>
                                    <Select
                                        key={`${finding?.id}-${formData.severity}`}
                                        value={formData.severity}
                                        onValueChange={(val) => handleChange('severity', val)}
                                    >
                                        <SelectTrigger className={cn("bg-slate-950/50 border-slate-800 text-white font-bold h-11", severities.find(s => s.value === formData.severity)?.color)}>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {severities.map((s) => (
                                                <SelectItem key={s.value} value={s.value} className={cn("font-bold my-1 mx-1 rounded-md", s.color)}>{s.label}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-3">
                                    <Label className="text-slate-400 text-xs font-semibold uppercase tracking-widest">Status</Label>
                                    <Select key={`${finding?.id}-${formData.status}`} value={formData.status} onValueChange={(val) => handleChange('status', val)}>
                                        <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white h-11"><SelectValue /></SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {statuses.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
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
                                    <Input value={formData.cvss_vector} onChange={(e) => handleChange('cvss_vector', e.target.value)} placeholder="CVSS:3.1/AV:N/AC:L..." className="bg-slate-950/50 border-slate-800 text-[10px] font-mono h-9" />
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
                    </div>
                </form>
            </div>

            {/* ── Save bar — only when dirty, pinned to the bottom ── */}
            <div className={cn(
                'sticky bottom-0 z-30 border-t transition-all duration-200',
                isDirty
                    ? 'border-blue-500/30 bg-slate-950/95 backdrop-blur-md'
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
                            onClick={handleSubmit}
                            disabled={updateFinding.isPending}
                            className={cn(
                                'gap-2 text-white',
                                hasConcurrentEditor
                                    ? 'bg-amber-600 hover:bg-amber-500'
                                    : 'bg-blue-600 hover:bg-blue-500'
                            )}
                            size="sm"
                            title={hasConcurrentEditor ? 'Another user is editing — saving will overwrite their work' : undefined}
                        >
                            {updateFinding.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
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

