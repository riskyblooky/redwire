'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Palette, Pencil, Trash2, Loader2, Server, FileText, Shield, Lock, Wrench, Target, FolderOpen, Radar, GitBranch } from 'lucide-react';
import { toast } from 'sonner';

import {
    useClientTypes,
    useCreateClientType,
    useUpdateClientType,
    useDeleteClientType,
} from '@/lib/hooks/use-clients';

import {
    useEngagementTypes,
    useCreateEngagementType,
    useUpdateEngagementType,
    useDeleteEngagementType,
    EngagementType,
} from '@/lib/hooks/use-engagement-types';

import {
    useConfigurableTypes,
    useCreateConfigurableType,
    useUpdateConfigurableType,
    useDeleteConfigurableType,
} from '@/lib/hooks/use-configurable-types';

// Reusable interface for both client and engagement types
interface TypeItem {
    id: string;
    name: string;
    description?: string | null;
    color: string;
    is_system: boolean;
    sort_order: number;
}

interface TypeManagerSectionProps {
    title: string;
    description: string;
    types: TypeItem[];
    isLoading: boolean;
    onSave: (data: { name: string; description: string; color: string }, editingId: string | null) => Promise<void>;
    onDelete: (id: string) => Promise<void>;
}

function TypeManagerSection({ title, description, types, isLoading, onSave, onDelete }: TypeManagerSectionProps) {
    const [editingType, setEditingType] = useState<TypeItem | null>(null);
    const [formData, setFormData] = useState({ name: '', description: '', color: '#6366f1' });
    const [isSaving, setIsSaving] = useState(false);

    const resetForm = () => {
        setEditingType(null);
        setFormData({ name: '', description: '', color: '#6366f1' });
    };

    const handleSave = async () => {
        if (!formData.name.trim()) return;
        setIsSaving(true);
        try {
            await onSave(formData, editingType?.id || null);
            resetForm();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || `Failed to save ${title.toLowerCase()}`);
        } finally {
            setIsSaving(false);
        }
    };

    const handleDelete = async (type: TypeItem) => {
        try {
            await onDelete(type.id);
            toast.success('Type deleted');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delete type');
        }
    };

    if (isLoading) {
        return (
            <Card className="border-slate-800 bg-slate-900/50">
                <CardContent className="flex items-center justify-center py-10">
                    <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader>
                <CardTitle className="text-white flex items-center gap-2 text-lg">
                    <Palette className="h-5 w-5 text-primary" />
                    {title}
                </CardTitle>
                <CardDescription>{description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Existing Types */}
                <div className="space-y-2">
                    {types.map(t => (
                        <div key={t.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                            <div className="flex items-center gap-3">
                                <div className="h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: t.color }} />
                                <div className="flex flex-col">
                                    <span className="text-sm text-white font-medium">{t.name}</span>
                                    {t.description && (
                                        <span className="text-xs text-slate-400">{t.description}</span>
                                    )}
                                </div>
                                {t.is_system && (
                                    <Badge variant="outline" className="text-[9px] py-0 px-1 text-slate-500 border-slate-600">
                                        System
                                    </Badge>
                                )}
                            </div>
                            <div className="flex items-center gap-1">
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-slate-400 hover:text-white"
                                    onClick={() => {
                                        setEditingType(t);
                                        setFormData({ name: t.name, description: t.description || '', color: t.color });
                                    }}
                                >
                                    <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                {!t.is_system && (
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-7 w-7 text-slate-400 hover:text-red-400"
                                        onClick={() => handleDelete(t)}
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                )}
                            </div>
                        </div>
                    ))}
                    {types.length === 0 && (
                        <p className="text-sm text-slate-500 text-center py-4">No types configured yet.</p>
                    )}
                </div>

                <Separator className="bg-slate-800" />

                {/* Add/Edit Form */}
                <div className="space-y-3">
                    <p className="text-xs text-slate-400 font-medium uppercase tracking-wider">
                        {editingType ? 'Edit Type' : 'Add New Type'}
                    </p>
                    <div className="flex items-center gap-2">
                        <Input
                            value={formData.name}
                            onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                            placeholder="Type name"
                            className="bg-slate-800/50 border-slate-700 text-white flex-1"
                        />
                        <input
                            type="color"
                            value={formData.color}
                            onChange={e => setFormData(prev => ({ ...prev, color: e.target.value }))}
                            className="w-10 h-10 rounded border border-slate-700 bg-transparent cursor-pointer"
                        />
                    </div>
                    <Input
                        value={formData.description}
                        onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
                        placeholder="Description (optional)"
                        className="bg-slate-800/50 border-slate-700 text-white"
                    />
                    <div className="flex gap-2">
                        {editingType && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={resetForm}
                                className="border-slate-700 text-slate-300"
                            >
                                Cancel
                            </Button>
                        )}
                        <Button
                            size="sm"
                            disabled={!formData.name.trim() || isSaving}
                            onClick={handleSave}
                            className="bg-primary hover:bg-primary/90"
                        >
                            {isSaving ? (
                                <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Saving...</>
                            ) : (
                                editingType ? 'Save' : 'Add Type'
                            )}
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}


function ConfigurableTypeSection({ category, title, description }: { category: string; title: string; description: string }) {
    const { data: types = [], isLoading } = useConfigurableTypes(category);
    const createType = useCreateConfigurableType(category);
    const updateType = useUpdateConfigurableType(category);
    const deleteType = useDeleteConfigurableType(category);

    return (
        <TypeManagerSection
            title={title}
            description={description}
            types={types}
            isLoading={isLoading}
            onSave={async (data, editingId) => {
                if (editingId) {
                    await updateType.mutateAsync({ id: editingId, ...data });
                    toast.success(`${title.replace(/s$/, '')} updated`);
                } else {
                    await createType.mutateAsync(data);
                    toast.success(`${title.replace(/s$/, '')} created`);
                }
            }}
            onDelete={async (id) => {
                await deleteType.mutateAsync(id);
            }}
        />
    );
}


export function TypeManagement() {
    // Client types
    const { data: clientTypes = [], isLoading: clientTypesLoading } = useClientTypes();
    const createClientType = useCreateClientType();
    const updateClientType = useUpdateClientType();
    const deleteClientType = useDeleteClientType();

    // Engagement types
    const { data: engagementTypes = [], isLoading: engagementTypesLoading } = useEngagementTypes();
    const createEngagementType = useCreateEngagementType();
    const updateEngagementType = useUpdateEngagementType();
    const deleteEngagementType = useDeleteEngagementType();

    return (
        <Tabs defaultValue="clients" className="space-y-4">
            <TabsList className="bg-slate-900 border border-slate-800 flex-wrap h-auto gap-1 p-1">
                <TabsTrigger value="clients" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <FolderOpen className="h-3.5 w-3.5" />
                    Client Types
                </TabsTrigger>
                <TabsTrigger value="engagements" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Target className="h-3.5 w-3.5" />
                    Engagement Types
                </TabsTrigger>
                <TabsTrigger value="assets" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Server className="h-3.5 w-3.5" />
                    Asset Types
                </TabsTrigger>
                <TabsTrigger value="testcases" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    Test Case Categories
                </TabsTrigger>
                <TabsTrigger value="findings" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Shield className="h-3.5 w-3.5" />
                    Finding Categories
                </TabsTrigger>
                <TabsTrigger value="vault" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Lock className="h-3.5 w-3.5" />
                    Vault Item Types
                </TabsTrigger>
                <TabsTrigger value="cleanup" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Wrench className="h-3.5 w-3.5" />
                    Cleanup Item Types
                </TabsTrigger>
                <TabsTrigger value="intel" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Radar className="h-3.5 w-3.5" />
                    Intel Types
                </TabsTrigger>
                <TabsTrigger value="infra" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <Server className="h-3.5 w-3.5" />
                    Infra Types
                </TabsTrigger>
                <TabsTrigger value="runbook" className="data-[state=active]:bg-slate-800 text-xs gap-1.5">
                    <GitBranch className="h-3.5 w-3.5" />
                    Runbook Types
                </TabsTrigger>
            </TabsList>

            <TabsContent value="clients">
                <TypeManagerSection
                    title="Client Types"
                    description="Configure how clients are categorized."
                    types={clientTypes}
                    isLoading={clientTypesLoading}
                    onSave={async (data, editingId) => {
                        if (editingId) {
                            await updateClientType.mutateAsync({ id: editingId, ...data });
                            toast.success('Client type updated');
                        } else {
                            await createClientType.mutateAsync(data);
                            toast.success('Client type created');
                        }
                    }}
                    onDelete={async (id) => {
                        await deleteClientType.mutateAsync(id);
                    }}
                />
            </TabsContent>

            <TabsContent value="engagements">
                <TypeManagerSection
                    title="Engagement Types"
                    description="Configure engagement type categories."
                    types={engagementTypes}
                    isLoading={engagementTypesLoading}
                    onSave={async (data, editingId) => {
                        if (editingId) {
                            await updateEngagementType.mutateAsync({ id: editingId, ...data });
                            toast.success('Engagement type updated');
                        } else {
                            await createEngagementType.mutateAsync(data);
                            toast.success('Engagement type created');
                        }
                    }}
                    onDelete={async (id) => {
                        await deleteEngagementType.mutateAsync(id);
                    }}
                />
            </TabsContent>

            <TabsContent value="assets">
                <ConfigurableTypeSection
                    category="asset"
                    title="Asset Types"
                    description="Configure how assets are categorized (e.g., IP Address, Domain, Server)."
                />
            </TabsContent>

            <TabsContent value="testcases">
                <ConfigurableTypeSection
                    category="testcase"
                    title="Test Case Categories"
                    description="Configure test case categories (e.g., Reconnaissance, Exploitation, Web Application)."
                />
            </TabsContent>

            <TabsContent value="findings">
                <ConfigurableTypeSection
                    category="finding"
                    title="Finding Categories"
                    description="Configure finding categories (e.g., Authentication, Injection, Configuration)."
                />
            </TabsContent>

            <TabsContent value="vault">
                <ConfigurableTypeSection
                    category="vault"
                    title="Vault Item Types"
                    description="Configure vault item types (e.g., Credential, Key, File, Note)."
                />
            </TabsContent>

            <TabsContent value="cleanup">
                <ConfigurableTypeSection
                    category="cleanup"
                    title="Cleanup Item Types"
                    description="Configure cleanup artifact types (e.g., SSH Key, Backdoor, Implant)."
                />
            </TabsContent>

            <TabsContent value="intel">
                <ConfigurableTypeSection
                    category="intel"
                    title="Intel Types"
                    description="Configure intelligence item types (e.g., CVE, Advisory, Exploit, Article)."
                />
            </TabsContent>

            <TabsContent value="infra">
                <ConfigurableTypeSection
                    category="infra"
                    title="Infrastructure Types"
                    description="Configure infrastructure asset types (e.g., VPS, C2 Server, Redirector, Proxy)."
                />
            </TabsContent>

            <TabsContent value="runbook">
                <ConfigurableTypeSection
                    category="runbook"
                    title="Runbook Types"
                    description="Configure runbook categories (e.g., Web Application, Network, Cloud, Internal)."
                />
            </TabsContent>
        </Tabs>
    );
}
