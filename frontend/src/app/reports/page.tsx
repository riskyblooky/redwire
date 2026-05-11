/**
 * reports/page.tsx — Reporting Center
 *
 * Report generation wizard. Allows the user to:
 *  1. Select a target engagement.
 *  2. Choose a report layout (loaded per-engagement).
 *  3. Pick an output format (PDF or Markdown).
 *  4. Optionally apply a report theme.
 *  5. Toggle severity filters to exclude specific finding severities.
 *  6. Click "Generate Report" to produce and download the document.
 *
 * Uses `useGenerateReport` mutation which downloads the generated file
 * as a blob. Layout and theme lists come from `useReportLayouts` and
 * `useReportThemes` hooks.
 */
'use client';

import { useState } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { FileText, Download, Loader2, Shield, Settings2, FileCode } from 'lucide-react';
import { useEngagements } from '@/lib/hooks/use-engagements';
import { toast } from 'sonner';
import { useGenerateReport, ReportConfiguration } from '@/lib/hooks/use-reports';
import { useReportLayouts } from '@/lib/hooks/use-report-layouts';
import { useReportThemes } from '@/lib/hooks/use-report-themes';

const severities = [
    { id: 'CRITICAL', label: 'Critical' },
    { id: 'HIGH', label: 'High' },
    { id: 'MEDIUM', label: 'Medium' },
    { id: 'LOW', label: 'Low' },
    { id: 'INFO', label: 'Info' },
];

export default function ReportsPage() {
    const { data: engagements = [], isLoading: isLoadingEngagements } = useEngagements();
    const generateReport = useGenerateReport();

    const [config, setConfig] = useState<ReportConfiguration>({
        engagement_id: '',
        layout_id: '',
        report_format: 'pdf',
        exclude_severities: [],
    });

    const { data: layouts = [] } = useReportLayouts(config.engagement_id || undefined);
    const { data: themes = [] } = useReportThemes();

    const handleSeverityToggle = (severity: string) => {
        setConfig(prev => ({
            ...prev,
            exclude_severities: prev.exclude_severities.includes(severity)
                ? prev.exclude_severities.filter(s => s !== severity)
                : [...prev.exclude_severities, severity]
        }));
    };

    const handleGenerate = async () => {
        if (!config.engagement_id) {
            toast.error('Please select an engagement');
            return;
        }
        if (!config.layout_id) {
            toast.error('Please select a report layout');
            return;
        }
        try {
            await generateReport.mutateAsync(config);
        } catch (error) {
            console.error('Failed to generate report:', error);
            toast.error('Failed to generate report');
        }
    };

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-4xl mx-auto">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                            <FileText className="h-8 w-8 text-green-500" />
                            Reporting Center
                        </h1>
                        <p className="text-slate-400 mt-1">Generate professional documentation for your operations</p>
                    </div>
                </div>

                <div className="grid gap-6 md:grid-cols-3">
                    {/* Left Column: Configuration */}
                    <div className="md:col-span-2 space-y-6">
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <CardTitle className="text-white text-lg flex items-center gap-2">
                                    <Settings2 className="h-5 w-5 text-primary" />
                                    Report Configuration
                                </CardTitle>
                                <CardDescription>Define the scope and format of your report</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {/* Engagement Selection */}
                                <div className="space-y-2">
                                    <Label className="text-slate-200">Target Engagement</Label>
                                    <Select
                                        value={config.engagement_id}
                                        onValueChange={(val) => setConfig(prev => ({ ...prev, engagement_id: val }))}
                                    >
                                        <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                                            <SelectValue placeholder="Select an engagement..." />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {engagements.map((eng) => (
                                                <SelectItem key={eng.id} value={eng.id}>{eng.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    {/* Report Layout */}
                                    <div className="space-y-2">
                                        <Label className="text-slate-200">Report Layout</Label>
                                        <Select
                                            value={config.layout_id}
                                            onValueChange={(val) => setConfig(prev => ({ ...prev, layout_id: val }))}
                                        >
                                            <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                                                <SelectValue placeholder={!config.engagement_id ? 'Select engagement first' : layouts.length === 0 ? 'No layouts available' : 'Select a layout...'} />
                                            </SelectTrigger>
                                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                {layouts.map((l) => (
                                                    <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Format */}
                                    <div className="space-y-2">
                                        <Label className="text-slate-200">Output Format</Label>
                                        <Select
                                            value={config.report_format}
                                            onValueChange={(val: any) => setConfig(prev => ({ ...prev, report_format: val }))}
                                        >
                                            <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                <SelectItem value="pdf">Adobe PDF (.pdf)</SelectItem>
                                                <SelectItem value="markdown">Markdown (.md)</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                {/* Theme Selection */}
                                <div className="space-y-2 pt-2">
                                    <Label className="text-slate-200">Report Theme</Label>
                                    <Select
                                        value={config.theme_id || '_none'}
                                        onValueChange={(val) => setConfig(prev => ({ ...prev, theme_id: val === '_none' ? undefined : val }))}
                                    >
                                        <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                                            <SelectValue placeholder="No theme (defaults)" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            <SelectItem value="_none">No theme (defaults)</SelectItem>
                                            {themes.map((t) => (
                                                <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Severity Filter */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Severity Filters</CardTitle>
                                <CardDescription>Exclude findings from specific severity levels</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="flex flex-wrap gap-4">
                                    {severities.map((s) => (
                                        <div key={s.id} className="flex items-center space-x-2 bg-slate-800/50 px-3 py-2 rounded-lg border border-slate-700">
                                            <Checkbox
                                                id={`sev-${s.id}`}
                                                checked={!config.exclude_severities.includes(s.id)}
                                                onCheckedChange={() => handleSeverityToggle(s.id)}
                                                className="border-slate-600"
                                            />
                                            <label htmlFor={`sev-${s.id}`} className="text-sm text-slate-300 cursor-pointer">{s.label}</label>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Right Column: Actions/Preview */}
                    <div className="space-y-6">
                        <Card className="border-slate-800 bg-linear-to-br from-green-500/10 to-transparent">
                            <CardHeader>
                                <CardTitle className="text-white text-sm uppercase tracking-wider font-bold">Actions</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <Button
                                    onClick={handleGenerate}
                                    disabled={generateReport.isPending || !config.engagement_id}
                                    className="w-full bg-green-600 hover:bg-green-700 text-white font-bold h-12 shadow-lg shadow-green-500/20"
                                >
                                    {generateReport.isPending ? (
                                        <>
                                            <Loader2 className="h-5 w-5 animate-spin mr-2" />
                                            Generating...
                                        </>
                                    ) : (
                                        <>
                                            <Download className="h-5 w-5 mr-2" />
                                            Generate Report
                                        </>
                                    )}
                                </Button>
                                <p className="text-[10px] text-slate-500 text-center uppercase font-medium">
                                    Reports are generated in real-time based on active discovery data.
                                </p>
                            </CardContent>
                        </Card>

                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardContent className="pt-6 space-y-4 text-center">
                                <div className="p-3 bg-slate-800 rounded-full w-fit mx-auto text-green-500">
                                    <Shield className="h-6 w-6" />
                                </div>
                                <div>
                                    <h4 className="text-white text-sm font-bold">Standard Templates</h4>
                                    <p className="text-xs text-slate-500 mt-1">Our reports follow industry standards for penetration testing and red teaming documentation.</p>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
}
