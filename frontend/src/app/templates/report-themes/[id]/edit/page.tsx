/**
 * templates/report-themes/[id]/edit/page.tsx — Report Theme Editor
 *
 * Full-page form for creating or editing PDF report themes.
 * Two-column layout:
 *
 * **Left column**
 *  - Basic Info: name, description, "set as default" toggle.
 *  - Colors: 6 color fields (primary, secondary, heading text, body
 *    text, table header bg/text) with picker swatches + hex inputs.
 *  - Typography: font family (Helvetica / Times / Courier), body size,
 *    heading size.
 *  - Page Layout: cover title, page size (US Letter / A4), header/
 *    footer text, cover page + page number toggles.
 *
 * **Right column**
 *  - Logo upload (≤ 500 KB, base64-encoded).
 *  - Live preview swatch showing simulated cover, heading, table, and
 *    footer rendered with the current theme settings.
 *
 * Sub-component: `ColorField` (label + swatch + hex input).
 */
'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import {
    ArrowLeft, Save, Loader2, Palette, Image as ImageIcon, X, Upload, Eye,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    useReportTheme,
    useCreateReportTheme,
    useUpdateReportTheme,
    ReportThemeCreate,
} from '@/lib/hooks/use-report-themes';

// Professional coordinated palettes for the theme editor preset dropdown.
// Each sets: primary/accent, secondary (dark bars), heading text, body text,
// table-header background + text.
const PALETTES: {
    name: string; primary: string; secondary: string; headerText: string;
    bodyText: string; tableHeaderBg: string; tableHeaderText: string;
}[] = [
    { name: 'Red Team (default)', primary: '#DC2626', secondary: '#1E293B', headerText: '#0F172A', bodyText: '#334155', tableHeaderBg: '#1E293B', tableHeaderText: '#FFFFFF' },
    { name: 'Corporate Blue', primary: '#2563EB', secondary: '#1E3A8A', headerText: '#1E293B', bodyText: '#334155', tableHeaderBg: '#1E3A8A', tableHeaderText: '#FFFFFF' },
    { name: 'Slate Monochrome', primary: '#475569', secondary: '#0F172A', headerText: '#0F172A', bodyText: '#334155', tableHeaderBg: '#334155', tableHeaderText: '#FFFFFF' },
    { name: 'Forest Green', primary: '#059669', secondary: '#064E3B', headerText: '#0F172A', bodyText: '#334155', tableHeaderBg: '#065F46', tableHeaderText: '#FFFFFF' },
    { name: 'Royal Purple', primary: '#7C3AED', secondary: '#3B0764', headerText: '#1E1B4B', bodyText: '#334155', tableHeaderBg: '#4C1D95', tableHeaderText: '#FFFFFF' },
    { name: 'Teal', primary: '#0D9488', secondary: '#134E4A', headerText: '#0F172A', bodyText: '#334155', tableHeaderBg: '#115E59', tableHeaderText: '#FFFFFF' },
    { name: 'Amber Gold', primary: '#D97706', secondary: '#451A03', headerText: '#1C1917', bodyText: '#44403C', tableHeaderBg: '#78350F', tableHeaderText: '#FFFFFF' },
    { name: 'Crimson', primary: '#BE123C', secondary: '#4C0519', headerText: '#1C1917', bodyText: '#3F3F46', tableHeaderBg: '#881337', tableHeaderText: '#FFFFFF' },
    { name: 'Indigo', primary: '#4F46E5', secondary: '#312E81', headerText: '#1E1B4B', bodyText: '#334155', tableHeaderBg: '#3730A3', tableHeaderText: '#FFFFFF' },
    { name: 'Ocean Navy', primary: '#0EA5E9', secondary: '#0C4A6E', headerText: '#0F172A', bodyText: '#334155', tableHeaderBg: '#075985', tableHeaderText: '#FFFFFF' },
];

interface ColorFieldProps {
    label: string;
    value: string;
    onChange: (v: string) => void;
    description?: string;
}

function ColorField({ label, value, onChange, description }: ColorFieldProps) {
    return (
        <div className="space-y-1.5">
            <Label className="text-slate-300 text-sm">{label}</Label>
            <div className="flex items-center gap-2">
                <label className="relative cursor-pointer">
                    <span
                        className="block w-10 h-10 rounded-lg border-2 border-slate-700 hover:border-slate-500 transition-colors"
                        style={{ backgroundColor: value }}
                    />
                    <input
                        type="color"
                        value={value}
                        onChange={e => onChange(e.target.value)}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                </label>
                <Input
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    className="w-28 bg-slate-950/50 border-slate-800 text-white font-mono text-sm uppercase"
                    maxLength={7}
                />
            </div>
            {description && <p className="text-xs text-slate-500">{description}</p>}
        </div>
    );
}

export default function ReportThemeEditPage() {
    const router = useRouter();
    const params = useParams();
    const themeId = params.id as string;
    const isNew = themeId === 'new';

    const { data: existing, isLoading } = useReportTheme(isNew ? null : themeId);
    const createMutation = useCreateReportTheme();
    const updateMutation = useUpdateReportTheme();

    const fileInputRef = useRef<HTMLInputElement>(null);

    // Form state
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [primaryColor, setPrimaryColor] = useState('#4F46E5');
    const [secondaryColor, setSecondaryColor] = useState('#7C3AED');
    const [headerTextColor, setHeaderTextColor] = useState('#1E293B');
    const [bodyTextColor, setBodyTextColor] = useState('#334155');
    const [tableHeaderBg, setTableHeaderBg] = useState('#4F46E5');
    const [tableHeaderText, setTableHeaderText] = useState('#FFFFFF');
    const [fontFamily, setFontFamily] = useState('Helvetica');
    const [fontSizeBody, setFontSizeBody] = useState(10);
    const [fontSizeHeading, setFontSizeHeading] = useState(20);
    const [logoBase64, setLogoBase64] = useState<string | null>(null);
    const [logoScale, setLogoScale] = useState(100);
    const [showPageNumbers, setShowPageNumbers] = useState(true);
    const [showPageXOfY, setShowPageXOfY] = useState(false);
    const [showCoverPage, setShowCoverPage] = useState(true);
    const [coverTitle, setCoverTitle] = useState('Security Assessment Report');
    const [headerText, setHeaderText] = useState('');
    const [footerText, setFooterText] = useState('CONFIDENTIAL');
    const [pageSize, setPageSize] = useState('letter');
    const [isDefault, setIsDefault] = useState(false);
    // Deepened appearance controls
    const [sevCritical, setSevCritical] = useState('#DC2626');
    const [sevHigh, setSevHigh] = useState('#EA580C');
    const [sevMedium, setSevMedium] = useState('#D97706');
    const [sevLow, setSevLow] = useState('#2563EB');
    const [sevInfo, setSevInfo] = useState('#64748B');
    const [tableZebra, setTableZebra] = useState(true);
    const [tableAltRowBg, setTableAltRowBg] = useState('#F8FAFC');
    const [tableGridColor, setTableGridColor] = useState('#CBD5E1');
    const [headerLeft, setHeaderLeft] = useState('');
    const [headerCenter, setHeaderCenter] = useState('');
    const [headerRight, setHeaderRight] = useState('');
    const [footerLeft, setFooterLeft] = useState('');
    const [footerCenter, setFooterCenter] = useState('');
    const [footerRight, setFooterRight] = useState('');
    const [showEvidenceFilenames, setShowEvidenceFilenames] = useState(true);
    const [showFindingSeverityBar, setShowFindingSeverityBar] = useState(true);
    const [showSectionTitleBackground, setShowSectionTitleBackground] = useState(true);
    const [coverTemplate, setCoverTemplate] = useState('banded');
    const [coverBackground, setCoverBackground] = useState<string | null>(null);
    const [coverSubtitle, setCoverSubtitle] = useState('');
    const [reportReference, setReportReference] = useState('');
    const [reportVersion, setReportVersion] = useState('');

    // Load existing theme
    useEffect(() => {
        if (!existing) return;
        setName(existing.name);
        setDescription(existing.description || '');
        setPrimaryColor(existing.primary_color);
        setSecondaryColor(existing.secondary_color);
        setHeaderTextColor(existing.header_text_color);
        setBodyTextColor(existing.body_text_color);
        setTableHeaderBg(existing.table_header_bg);
        setTableHeaderText(existing.table_header_text);
        setFontFamily(existing.font_family);
        setFontSizeBody(existing.font_size_body);
        setFontSizeHeading(existing.font_size_heading);
        setLogoBase64(existing.logo_base64 || null);
        setLogoScale(existing.logo_scale ?? 100);
        setShowPageNumbers(existing.show_page_numbers);
        setShowPageXOfY(existing.show_page_x_of_y ?? false);
        setShowCoverPage(existing.show_cover_page);
        setCoverTitle(existing.cover_title);
        setHeaderText(existing.header_text || '');
        setFooterText(existing.footer_text || '');
        setPageSize(existing.page_size);
        setIsDefault(existing.is_default);
        setSevCritical(existing.severity_critical_color || '#DC2626');
        setSevHigh(existing.severity_high_color || '#EA580C');
        setSevMedium(existing.severity_medium_color || '#D97706');
        setSevLow(existing.severity_low_color || '#2563EB');
        setSevInfo(existing.severity_info_color || '#64748B');
        setTableZebra(existing.table_zebra_enabled ?? true);
        setTableAltRowBg(existing.table_alt_row_bg || '#F8FAFC');
        setTableGridColor(existing.table_grid_color || '#CBD5E1');
        setHeaderLeft(existing.header_left || '');
        setHeaderCenter(existing.header_center || '');
        setHeaderRight(existing.header_right || '');
        setFooterLeft(existing.footer_left || '');
        setFooterCenter(existing.footer_center || '');
        setFooterRight(existing.footer_right || '');
        setShowEvidenceFilenames(existing.show_evidence_filenames ?? true);
        setShowFindingSeverityBar(existing.show_finding_severity_bar ?? true);
        setShowSectionTitleBackground(existing.show_section_title_background ?? true);
        setCoverTemplate(existing.cover_template || 'banded');
        setCoverBackground(existing.cover_background_base64 || null);
        setCoverSubtitle(existing.cover_subtitle || '');
        setReportReference(existing.report_reference || '');
        setReportVersion(existing.report_version || '');
    }, [existing]);

    const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 500_000) {
            toast.error('Logo must be under 500KB');
            return;
        }
        const reader = new FileReader();
        reader.onload = () => setLogoBase64(reader.result as string);
        reader.readAsDataURL(file);
    };

    const handleCoverBgUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 2_000_000) {
            toast.error('Cover image must be under 2MB');
            return;
        }
        const reader = new FileReader();
        reader.onload = () => setCoverBackground(reader.result as string);
        reader.readAsDataURL(file);
    };

    const saving = createMutation.isPending || updateMutation.isPending;

    const handleSave = async () => {
        if (!name.trim()) {
            toast.error('Theme name is required');
            return;
        }
        const payload: ReportThemeCreate = {
            name: name.trim(),
            description: description.trim() || undefined,
            primary_color: primaryColor,
            secondary_color: secondaryColor,
            header_text_color: headerTextColor,
            body_text_color: bodyTextColor,
            table_header_bg: tableHeaderBg,
            table_header_text: tableHeaderText,
            font_family: fontFamily,
            font_size_body: fontSizeBody,
            font_size_heading: fontSizeHeading,
            // Clearable text/image fields send their raw value (incl. '' / null)
            // so emptying a field actually clears it on update — `|| undefined`
            // would drop the key and leave the old value in place.
            logo_base64: logoBase64,
            logo_scale: logoScale,
            show_page_numbers: showPageNumbers,
            show_page_x_of_y: showPageXOfY,
            show_cover_page: showCoverPage,
            cover_title: coverTitle,
            header_text: headerText,
            footer_text: footerText,
            page_size: pageSize,
            is_default: isDefault,
            severity_critical_color: sevCritical,
            severity_high_color: sevHigh,
            severity_medium_color: sevMedium,
            severity_low_color: sevLow,
            severity_info_color: sevInfo,
            table_zebra_enabled: tableZebra,
            table_alt_row_bg: tableAltRowBg,
            table_grid_color: tableGridColor,
            header_left: headerLeft,
            header_center: headerCenter,
            header_right: headerRight,
            footer_left: footerLeft,
            footer_center: footerCenter,
            footer_right: footerRight,
            show_evidence_filenames: showEvidenceFilenames,
            show_finding_severity_bar: showFindingSeverityBar,
            show_section_title_background: showSectionTitleBackground,
            cover_template: coverTemplate,
            cover_background_base64: coverBackground,
            cover_subtitle: coverSubtitle,
            report_reference: reportReference,
            report_version: reportVersion,
        };

        try {
            if (isNew) {
                await createMutation.mutateAsync(payload);
                toast.success('Report theme created');
            } else {
                await updateMutation.mutateAsync({ id: themeId, ...payload });
                toast.success('Report theme updated');
            }
            router.push('/templates?tab=report-themes');
        } catch (err: any) {
            toast.error(err?.response?.data?.detail || 'Failed to save theme');
        }
    };

    if (!isNew && isLoading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center h-80">
                    <Loader2 className="h-8 w-8 animate-spin text-slate-500" />
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Button variant="ghost" size="icon" onClick={() => router.push('/templates?tab=report-themes')}>
                            <ArrowLeft className="h-5 w-5 text-slate-400" />
                        </Button>
                        <div className="flex items-center gap-2">
                            <div className="p-2 rounded-lg bg-linear-to-br from-purple-500/20 to-pink-500/20">
                                <Palette className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                                <h1 className="text-xl font-bold text-white">{isNew ? 'Create' : 'Edit'} Report Theme</h1>
                                <p className="text-sm text-slate-400">Customize PDF report visual settings</p>
                            </div>
                        </div>
                    </div>
                    <Button
                        onClick={handleSave}
                        disabled={saving || !name.trim()}
                        className="bg-primary hover:bg-primary/90 text-white gap-2"
                    >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        {isNew ? 'Create Theme' : 'Save Changes'}
                    </Button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left column — Main settings */}
                    <div className="lg:col-span-2 space-y-6">
                        {/* Basic Info */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Basic Info</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Theme Name*</Label>
                                        <Input
                                            value={name}
                                            onChange={e => setName(e.target.value)}
                                            placeholder="e.g. Corporate Blue"
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Description</Label>
                                        <Input
                                            value={description}
                                            onChange={e => setDescription(e.target.value)}
                                            placeholder="Optional"
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center gap-3">
                                    <Switch checked={isDefault} onCheckedChange={setIsDefault} />
                                    <Label className="text-slate-300">Set as default theme</Label>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Colors */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Colors</CardTitle>
                                <CardDescription>Apply a preset palette, or click a swatch / type a hex code</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="mb-5 space-y-1.5">
                                    <Label className="text-slate-300 text-sm">Preset palette</Label>
                                    <Select value="" onValueChange={(name) => {
                                        const p = PALETTES.find(p => p.name === name);
                                        if (!p) return;
                                        setPrimaryColor(p.primary); setSecondaryColor(p.secondary);
                                        setHeaderTextColor(p.headerText); setBodyTextColor(p.bodyText);
                                        setTableHeaderBg(p.tableHeaderBg); setTableHeaderText(p.tableHeaderText);
                                    }}>
                                        <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white">
                                            <SelectValue placeholder="Choose a professional palette…" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                            {PALETTES.map(p => (
                                                <SelectItem key={p.name} value={p.name} className="focus:bg-indigo-500/20">
                                                    <span className="flex items-center gap-2">
                                                        <span className="flex gap-0.5">
                                                            {[p.primary, p.secondary, p.tableHeaderBg].map((c, i) => (
                                                                <span key={i} className="inline-block w-3 h-3 rounded-sm border border-slate-700" style={{ backgroundColor: c }} />
                                                            ))}
                                                        </span>
                                                        {p.name}
                                                    </span>
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <p className="text-xs text-slate-500">Applies coordinated colors below — tweak any of them afterward.</p>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
                                    <ColorField label="Primary / Accent" value={primaryColor} onChange={setPrimaryColor} description="Cover title, accent elements" />
                                    <ColorField label="Secondary" value={secondaryColor} onChange={setSecondaryColor} description="Supplementary accent" />
                                    <ColorField label="Section Headings" value={headerTextColor} onChange={setHeaderTextColor} description="All heading text" />
                                    <ColorField label="Body Text" value={bodyTextColor} onChange={setBodyTextColor} description="Paragraphs & labels" />
                                    <ColorField label="Table Header BG" value={tableHeaderBg} onChange={setTableHeaderBg} description="Background" />
                                    <ColorField label="Table Header Text" value={tableHeaderText} onChange={setTableHeaderText} description="Foreground" />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Severity Colors */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Severity Colors</CardTitle>
                                <CardDescription>Used for finding badges, the severity chart, and card accents</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
                                    <ColorField label="Critical" value={sevCritical} onChange={setSevCritical} />
                                    <ColorField label="High" value={sevHigh} onChange={setSevHigh} />
                                    <ColorField label="Medium" value={sevMedium} onChange={setSevMedium} />
                                    <ColorField label="Low" value={sevLow} onChange={setSevLow} />
                                    <ColorField label="Info" value={sevInfo} onChange={setSevInfo} />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Tables */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Tables</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex items-center gap-3">
                                    <Switch checked={tableZebra} onCheckedChange={setTableZebra} />
                                    <Label className="text-slate-300">Zebra striping (alternating row shading)</Label>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
                                    <ColorField label="Alt Row Background" value={tableAltRowBg} onChange={setTableAltRowBg} description="Shaded rows" />
                                    <ColorField label="Grid Lines" value={tableGridColor} onChange={setTableGridColor} description="Row dividers" />
                                </div>
                            </CardContent>
                        </Card>

                        {/* Typography */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Typography</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Font Family</Label>
                                        <Select value={fontFamily} onValueChange={setFontFamily}>
                                            <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                <SelectItem value="Helvetica" className="focus:bg-indigo-500/20">Helvetica</SelectItem>
                                                <SelectItem value="Times-Roman" className="focus:bg-indigo-500/20">Times Roman</SelectItem>
                                                <SelectItem value="Courier" className="focus:bg-indigo-500/20">Courier</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Body Size (pt)</Label>
                                        <Input
                                            type="number"
                                            min={8} max={16}
                                            value={fontSizeBody}
                                            onChange={e => setFontSizeBody(Number(e.target.value))}
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Heading Size (pt)</Label>
                                        <Input
                                            type="number"
                                            min={14} max={36}
                                            value={fontSizeHeading}
                                            onChange={e => setFontSizeHeading(Number(e.target.value))}
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Page Layout */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg">Page Layout</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Cover Title</Label>
                                        <Input
                                            value={coverTitle}
                                            onChange={e => setCoverTitle(e.target.value)}
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Page Size</Label>
                                        <Select value={pageSize} onValueChange={setPageSize}>
                                            <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                <SelectItem value="letter" className="focus:bg-indigo-500/20">US Letter</SelectItem>
                                                <SelectItem value="a4" className="focus:bg-indigo-500/20">A4</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Header Text</Label>
                                        <Input
                                            value={headerText}
                                            onChange={e => setHeaderText(e.target.value)}
                                            placeholder="Optional running header"
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-slate-300">Footer Text</Label>
                                        <Input
                                            value={footerText}
                                            onChange={e => setFooterText(e.target.value)}
                                            placeholder="e.g. CONFIDENTIAL"
                                            className="bg-slate-950/50 border-slate-800 text-white"
                                        />
                                    </div>
                                </div>
                                <div className="flex flex-wrap gap-6 pt-2">
                                    <div className="flex items-center gap-3">
                                        <Switch checked={showCoverPage} onCheckedChange={setShowCoverPage} />
                                        <Label className="text-slate-300">Cover Page</Label>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Switch checked={showPageNumbers} onCheckedChange={setShowPageNumbers} />
                                        <Label className="text-slate-300">Page Numbers</Label>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Switch checked={showPageXOfY} onCheckedChange={setShowPageXOfY} disabled={!showPageNumbers} />
                                        <Label className="text-slate-300">Show “of N” total</Label>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Switch checked={showEvidenceFilenames} onCheckedChange={setShowEvidenceFilenames} />
                                        <Label className="text-slate-300">Show evidence filenames</Label>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Switch checked={showSectionTitleBackground} onCheckedChange={setShowSectionTitleBackground} />
                                        <Label className="text-slate-300">Title background block</Label>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Switch checked={showFindingSeverityBar} onCheckedChange={setShowFindingSeverityBar} />
                                        <Label className="text-slate-300">Finding severity bar</Label>
                                    </div>
                                </div>

                                <div className="pt-2 space-y-3">
                                    <Label className="text-slate-300 text-sm font-semibold">Header zones (left / center / right)</Label>
                                    <p className="text-xs text-slate-500 -mt-1">When set, these supersede the single Header Text above.</p>
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                        <Input value={headerLeft} onChange={e => setHeaderLeft(e.target.value)} placeholder="Left" className="bg-slate-950/50 border-slate-800 text-white" />
                                        <Input value={headerCenter} onChange={e => setHeaderCenter(e.target.value)} placeholder="Center" className="bg-slate-950/50 border-slate-800 text-white" />
                                        <Input value={headerRight} onChange={e => setHeaderRight(e.target.value)} placeholder="Right" className="bg-slate-950/50 border-slate-800 text-white" />
                                    </div>
                                    <Label className="text-slate-300 text-sm font-semibold pt-1 block">Footer zones (left / center / right)</Label>
                                    <p className="text-xs text-slate-500 -mt-1">Page number takes the right zone unless Footer Right is set. (When a marking profile is active, its banner carries the classification and the legacy footer text is suppressed.)</p>
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                        <Input value={footerLeft} onChange={e => setFooterLeft(e.target.value)} placeholder="Left" className="bg-slate-950/50 border-slate-800 text-white" />
                                        <Input value={footerCenter} onChange={e => setFooterCenter(e.target.value)} placeholder="Center" className="bg-slate-950/50 border-slate-800 text-white" />
                                        <Input value={footerRight} onChange={e => setFooterRight(e.target.value)} placeholder="Right" className="bg-slate-950/50 border-slate-800 text-white" />
                                    </div>
                                </div>

                                <div className="pt-2 space-y-3">
                                    <Label className="text-slate-300 text-sm font-semibold">Cover</Label>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        <div className="space-y-1.5">
                                            <Label className="text-slate-400 text-xs">Cover template</Label>
                                            <Select value={coverTemplate} onValueChange={setCoverTemplate}>
                                                <SelectTrigger className="bg-slate-950/50 border-slate-800 text-white">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                    <SelectItem value="banded">Banded (geometric accents)</SelectItem>
                                                    <SelectItem value="minimal">Minimal (clean)</SelectItem>
                                                    <SelectItem value="full_bleed_image">Full-bleed image</SelectItem>
                                                    <SelectItem value="classified">Classified (banner frame)</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-slate-400 text-xs">Cover background image</Label>
                                            <div className="flex items-center gap-2">
                                                <input type="file" accept="image/png,image/jpeg" className="hidden" id="cover-bg-upload" onChange={handleCoverBgUpload} />
                                                <Button type="button" variant="outline" size="sm" className="border-slate-700 text-slate-300" onClick={() => document.getElementById('cover-bg-upload')?.click()}>
                                                    <Upload className="h-3.5 w-3.5 mr-1" /> {coverBackground ? 'Replace' : 'Upload'}
                                                </Button>
                                                {coverBackground && (
                                                    <Button type="button" variant="ghost" size="sm" className="text-red-400" onClick={() => setCoverBackground(null)}>
                                                        <X className="h-3.5 w-3.5" />
                                                    </Button>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <Label className="text-slate-300 text-sm font-semibold pt-1 block">Cover metadata</Label>
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                        <Input value={coverSubtitle} onChange={e => setCoverSubtitle(e.target.value)} placeholder="Subtitle" className="bg-slate-950/50 border-slate-800 text-white" />
                                        <Input value={reportReference} onChange={e => setReportReference(e.target.value)} placeholder="Reference #" className="bg-slate-950/50 border-slate-800 text-white" />
                                        <Input value={reportVersion} onChange={e => setReportVersion(e.target.value)} placeholder="Version" className="bg-slate-950/50 border-slate-800 text-white" />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Right column — Logo & Preview */}
                    <div className="space-y-6">
                        {/* Logo */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg flex items-center gap-2">
                                    <ImageIcon className="h-4 w-4 text-indigo-400" /> Logo
                                </CardTitle>
                                <CardDescription>Displayed on the cover page. Max 500KB.</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept="image/png,image/jpeg,image/svg+xml"
                                    className="hidden"
                                    onChange={handleLogoUpload}
                                />
                                {logoBase64 ? (
                                    <div className="space-y-3">
                                        <div className="relative group">
                                            <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4 flex items-center justify-center overflow-hidden" style={{ minHeight: '64px' }}>
                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                <img src={logoBase64} alt="Logo preview" className="object-contain" style={{ height: `${Math.max(20, 0.7 * logoScale)}px`, maxWidth: '100%' }} />
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="absolute top-2 right-2 h-7 w-7 bg-slate-900/80 hover:bg-red-500/20 text-slate-400 hover:text-red-400"
                                                onClick={() => setLogoBase64(null)}
                                            >
                                                <X className="h-4 w-4" />
                                            </Button>
                                        </div>
                                        <div className="space-y-1.5">
                                            <div className="flex items-center justify-between">
                                                <Label className="text-slate-300 text-sm">Logo scale</Label>
                                                <span className="text-xs text-slate-400 font-mono">{logoScale}%</span>
                                            </div>
                                            <Slider value={[logoScale]} onValueChange={(v) => setLogoScale(v[0])} min={25} max={300} step={5} />
                                            <p className="text-xs text-slate-500">Aspect ratio is always preserved; scale adjusts the height.</p>
                                        </div>
                                    </div>
                                ) : (
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        className="w-full border-2 border-dashed border-slate-800 rounded-lg py-8 flex flex-col items-center gap-2 hover:border-indigo-500/40 transition-colors"
                                    >
                                        <Upload className="h-6 w-6 text-slate-500" />
                                        <span className="text-sm text-slate-400">Click to upload</span>
                                        <span className="text-xs text-slate-500">PNG, JPEG, or SVG</span>
                                    </button>
                                )}
                            </CardContent>
                        </Card>

                        {/* Live Preview Swatch */}
                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <CardTitle className="text-white text-lg flex items-center gap-2">
                                    <Eye className="h-4 w-4 text-indigo-400" /> Preview
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="rounded-lg border border-slate-800 bg-white p-4 space-y-3">
                                    {/* Simulated cover */}
                                    {showCoverPage && (
                                        <div className="text-center pb-3 border-b" style={{ borderColor: primaryColor + '40' }}>
                                            {logoBase64 && (
                                                // eslint-disable-next-line @next/next/no-img-element
                                                <img src={logoBase64} alt="Logo" className="h-8 mx-auto mb-2 object-contain" />
                                            )}
                                            <p className="font-bold text-sm" style={{ color: primaryColor, fontFamily }}>{coverTitle}</p>
                                            <p className="text-[10px]" style={{ color: bodyTextColor, fontFamily }}>Engagement Name</p>
                                        </div>
                                    )}

                                    {/* Simulated heading */}
                                    <div>
                                        <p className="text-xs font-bold" style={{ color: headerTextColor, fontFamily, fontSize: `${Math.max(fontSizeHeading * 0.55, 10)}px` }}>
                                            Section Heading
                                        </p>
                                        <p className="text-[10px] mt-1 leading-relaxed" style={{ color: bodyTextColor, fontFamily, fontSize: `${Math.max(fontSizeBody * 0.85, 8)}px` }}>
                                            Lorem ipsum dolor sit amet, consectetur adipiscing elit.
                                        </p>
                                    </div>

                                    {/* Simulated table */}
                                    <div className="rounded overflow-hidden text-[9px]">
                                        <div className="flex" style={{ backgroundColor: tableHeaderBg }}>
                                            <span className="flex-1 px-2 py-1 font-bold" style={{ color: tableHeaderText, fontFamily }}>Finding</span>
                                            <span className="w-16 px-2 py-1 text-center font-bold" style={{ color: tableHeaderText, fontFamily }}>Severity</span>
                                        </div>
                                        <div className="flex border-b" style={{ borderColor: '#e2e8f0' }}>
                                            <span className="flex-1 px-2 py-1" style={{ color: bodyTextColor, fontFamily }}>SQL Injection</span>
                                            <span className="w-16 px-2 py-1 text-center" style={{ color: bodyTextColor, fontFamily }}>Critical</span>
                                        </div>
                                        <div className="flex">
                                            <span className="flex-1 px-2 py-1" style={{ color: bodyTextColor, fontFamily }}>Weak Cipher</span>
                                            <span className="w-16 px-2 py-1 text-center" style={{ color: bodyTextColor, fontFamily }}>Medium</span>
                                        </div>
                                    </div>

                                    {/* Simulated footer */}
                                    <div className="flex items-center justify-between text-[8px] pt-2 border-t" style={{ borderColor: '#e2e8f0', color: '#94a3b8', fontFamily }}>
                                        <span>{footerText || '\u00A0'}</span>
                                        {showPageNumbers && <span>Page 1</span>}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
}
