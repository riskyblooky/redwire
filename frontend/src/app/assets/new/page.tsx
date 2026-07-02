/**
 * assets/new/page.tsx — Create Asset Page
 *
 * Simple form for registering a new target asset within an engagement.
 * Fields: engagement selector (lockable via ?engagementId query param),
 * name, type (from configurable types), identifier (monospaced input),
 * description, and internal notes (both Markdown editors).
 * Redirects to the engagement's assets tab on successful creation.
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
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import { useCreateAsset } from '@/lib/hooks/use-assets';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { useConfigurableTypes } from '@/lib/hooks/use-configurable-types';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';


export default function NewAssetPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const engagementIdParam = searchParams.get('engagementId');

    const createAsset = useCreateAsset();
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const { data: assetTypes = [] } = useConfigurableTypes('asset');

    const [formData, setFormData] = useState({
        name: '',
        engagement_id: engagementIdParam || '',
        asset_type: 'Domain',
        identifier: '',
        description: '',
        notes: '',
    });

    const handleChange = (field: string, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!formData.engagement_id) {
            toast.error('Please select an engagement');
            return;
        }

        try {
            await createAsset.mutateAsync(formData);
            router.push(`/engagements/${formData.engagement_id}?tab=assets`);
        } catch (error: any) {
            console.error('Failed to create asset:', error);
            toast.error(apiErrorMessage(error, 'Failed to create asset'));
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 w-full">
                {/* Page Header */}
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                            const backPath = engagementIdParam
                                ? `/engagements/${engagementIdParam}?tab=assets`
                                : '/assets';
                            router.push(backPath);
                        }}
                        className="text-slate-400 hover:text-white hover:bg-slate-800"
                    >
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div>
                        <h1 className="text-3xl font-bold text-white">Add New Asset</h1>
                        <p className="text-slate-400 mt-1">Register a new target asset for testing</p>
                    </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit}>
                    <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader>
                            <CardTitle className="text-white">Asset Details</CardTitle>
                            <CardDescription>Provide information about the target asset</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {/* Engagement Selection */}
                            <div className="space-y-2">
                                <Label htmlFor="engagement_id" className="text-slate-200">
                                    Engagement *
                                </Label>
                                <Select
                                    value={formData.engagement_id}
                                    onValueChange={(value) => handleChange('engagement_id', value)}
                                    disabled={!!engagementIdParam}
                                >
                                    <SelectTrigger id="engagement_id" className="bg-slate-800/50 border-slate-700 text-white">
                                        <SelectValue placeholder="Select an engagement..." />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                        {isLoadingEngagements ? (
                                            <div className="p-2 flex justify-center">
                                                <Loader2 className="h-4 w-4 animate-spin" />
                                            </div>
                                        ) : engagements.length === 0 ? (
                                            <div className="p-2 text-sm text-slate-400">No engagements found</div>
                                        ) : (
                                            engagements.map((eng) => (
                                                <SelectItem key={eng.id} value={eng.id}>
                                                    {eng.name} ({eng.client_name})
                                                </SelectItem>
                                            ))
                                        )}
                                    </SelectContent>
                                </Select>
                            </div>

                            {/* Name */}
                            <div className="space-y-2">
                                <Label htmlFor="name" className="text-slate-200">
                                    Asset Name *
                                </Label>
                                <Input
                                    id="name"
                                    value={formData.name}
                                    onChange={(e) => handleChange('name', e.target.value)}
                                    placeholder="e.g., Corporate Website, External VPN"
                                    required
                                    className="bg-slate-800/50 border-slate-700 text-white"
                                />
                            </div>

                            {/* Type and Identifier */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div className="space-y-2">
                                    <Label htmlFor="asset_type" className="text-slate-200">
                                        Asset Type *
                                    </Label>
                                    <Select value={formData.asset_type} onValueChange={(value) => handleChange('asset_type', value)}>
                                        <SelectTrigger id="asset_type" className="bg-slate-800/50 border-slate-700 text-white">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {assetTypes.map((type) => (
                                                <SelectItem key={type.id} value={type.name}>
                                                    {type.name}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="identifier" className="text-slate-200">
                                        Identifier *
                                    </Label>
                                    <Input
                                        id="identifier"
                                        value={formData.identifier}
                                        onChange={(e) => handleChange('identifier', e.target.value)}
                                        placeholder="e.g., 192.168.1.1, example.com, https://app.acme.com"
                                        required
                                        className="bg-slate-800/50 border-slate-700 text-white font-mono"
                                    />
                                </div>
                            </div>

                            {/* Description */}
                            <div className="space-y-2">
                                <Label htmlFor="description" className="text-slate-200">
                                    Description
                                </Label>
                                <MarkdownEditor
                                    id="description"
                                    value={formData.description}
                                    onChange={(val) => handleChange('description', val)}
                                    placeholder="Brief description of the asset..."
                                    minHeight="150px"
                                />
                            </div>

                            {/* Notes */}
                            <div className="space-y-2">
                                <Label htmlFor="notes" className="text-slate-200">
                                    Internal Notes
                                </Label>
                                <MarkdownEditor
                                    id="notes"
                                    value={formData.notes}
                                    onChange={(val) => handleChange('notes', val)}
                                    placeholder="Any internal notes about this asset..."
                                    minHeight="150px"
                                />
                            </div>

                            {/* Ports note */}
                            <div className="rounded-lg border border-dashed border-slate-700 bg-slate-800/20 p-4 flex items-start gap-3">
                                <div className="h-8 w-8 rounded-md bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center shrink-0 mt-0.5">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-cyan-400"><rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/><path d="M12 12V8"/></svg>
                                </div>
                                <div>
                                    <p className="text-sm text-slate-300 font-medium">Ports &amp; Services</p>
                                    <p className="text-xs text-slate-500 mt-0.5">Ports can be added after the asset is created. You'll be able to manage ports from the edit page.</p>
                                </div>
                            </div>

                            {/* Actions */}
                            <div className="flex justify-end gap-3 pt-4">
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => {
                                        const backPath = engagementIdParam
                                            ? `/engagements/${engagementIdParam}?tab=assets`
                                            : '/assets';
                                        router.push(backPath);
                                    }}
                                    className="border-slate-700 text-slate-300 hover:bg-slate-800"
                                    disabled={createAsset.isPending}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    type="submit"
                                    disabled={createAsset.isPending}
                                    className="bg-primary hover:bg-primary/90 text-white"
                                >
                                    {createAsset.isPending ? (
                                        <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            Creating...
                                        </>
                                    ) : (
                                        <>
                                            <Save className="h-4 w-4 mr-2" />
                                            Create Asset
                                        </>
                                    )}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </form>
            </div>
        </DashboardLayout>
    );
}
