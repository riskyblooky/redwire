'use client';

import { useState, useMemo, useEffect } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Search, Bug, CheckSquare, Loader2, Link as LinkIcon, CheckCircle } from 'lucide-react';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';

type LinkKind = 'finding' | 'testcase';
export interface EvidenceLinkSelection {
    findingId: string | null;
    testcaseId: string | null;
}

interface EvidenceLinkDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    engagementId: string;
    /** The evidence being re-linked (for its current target + filename). */
    evidence: { id: string; original_filename: string; finding_id?: string | null; testcase_id?: string | null } | null;
    onApply: (selection: EvidenceLinkSelection) => Promise<void>;
}

const TABS: { key: LinkKind; label: string; icon: React.ElementType; color: string; selectedBg: string; selectedBorder: string }[] = [
    { key: 'finding',  label: 'Findings',   icon: Bug,         color: 'text-red-400',     selectedBg: 'bg-red-500',     selectedBorder: 'border-red-500/30 bg-red-500/5' },
    { key: 'testcase', label: 'Test Cases', icon: CheckSquare, color: 'text-emerald-400', selectedBg: 'bg-emerald-500', selectedBorder: 'border-emerald-500/30 bg-emerald-500/5' },
];

/**
 * Single-target link picker for an attachment (evidence). Evidence attaches to
 * at most one finding OR one test case, so this is a radio-style pick with a
 * clear ("Not linked") option — not the multi-select LinkEntityDialog.
 */
export function EvidenceLinkDialog({ open, onOpenChange, engagementId, evidence, onApply }: EvidenceLinkDialogProps) {
    const [activeTab, setActiveTab] = useState<LinkKind>('finding');
    const [search, setSearch] = useState('');
    const [selKind, setSelKind] = useState<LinkKind | null>(null);
    const [selId, setSelId] = useState<string | null>(null);
    const [isApplying, setIsApplying] = useState(false);

    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: testcases = [] } = useTestCases(engagementId);

    // Seed selection + active tab from the evidence's current link on open.
    useEffect(() => {
        if (!open || !evidence) return;
        if (evidence.finding_id) {
            setSelKind('finding'); setSelId(evidence.finding_id); setActiveTab('finding');
        } else if (evidence.testcase_id) {
            setSelKind('testcase'); setSelId(evidence.testcase_id); setActiveTab('testcase');
        } else {
            setSelKind(null); setSelId(null); setActiveTab('finding');
        }
        setSearch('');
    }, [open, evidence]);

    const items = useMemo(() => {
        const term = search.toLowerCase();
        const finding = findings
            .map(f => ({ id: f.id, label: f.title, sub: f.severity as string | undefined }))
            .filter(i => i.label.toLowerCase().includes(term));
        const testcase = testcases
            .map(t => ({ id: t.id, label: t.title, sub: (t.category || undefined) as string | undefined }))
            .filter(i => i.label.toLowerCase().includes(term));
        return { finding, testcase };
    }, [findings, testcases, search]);

    const activeCfg = TABS.find(t => t.key === activeTab)!;
    const ActiveIcon = activeCfg.icon;
    const currentItems = items[activeTab];

    const toggleSelect = (id: string) => {
        if (selKind === activeTab && selId === id) { setSelKind(null); setSelId(null); }
        else { setSelKind(activeTab); setSelId(id); }
    };

    const handleApply = async () => {
        setIsApplying(true);
        try {
            await onApply({
                findingId: selKind === 'finding' ? selId : null,
                testcaseId: selKind === 'testcase' ? selId : null,
            });
            onOpenChange(false);
        } finally {
            setIsApplying(false);
        }
    };

    const selectedLabel = selId
        ? (selKind === 'finding' ? findings.find(f => f.id === selId)?.title : testcases.find(t => t.id === selId)?.title)
        : null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[560px] p-0 gap-0 overflow-hidden max-h-[80vh] flex flex-col">
                <DialogHeader className="px-4 pt-4 pb-3 border-b border-slate-800/60">
                    <DialogTitle className="text-base font-semibold flex items-center gap-2">
                        <LinkIcon className="h-4 w-4 text-indigo-400" />
                        Link Attachment
                    </DialogTitle>
                    <p className="text-xs text-slate-500 mt-0.5 truncate">
                        Attach <span className="text-slate-300">{evidence?.original_filename}</span> to a finding or test case.
                    </p>
                </DialogHeader>

                {/* Tabs */}
                <div className="flex border-b border-slate-800/60 px-2 gap-0.5">
                    {TABS.map(tab => {
                        const Icon = tab.icon;
                        const hasSel = selKind === tab.key;
                        return (
                            <button
                                key={tab.key}
                                onClick={() => { setActiveTab(tab.key); setSearch(''); }}
                                className={cn(
                                    "flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-all border-b-2 -mb-px",
                                    activeTab === tab.key ? "border-indigo-400 text-indigo-300" : "border-transparent text-slate-500 hover:text-slate-300"
                                )}
                            >
                                <Icon className={cn("h-3.5 w-3.5", activeTab === tab.key ? tab.color : "")} />
                                {tab.label}
                                {hasSel && <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />}
                            </button>
                        );
                    })}
                </div>

                {/* Search */}
                <div className="px-4 py-2 border-b border-slate-800/40">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
                        <Input
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder={`Search ${activeCfg.label.toLowerCase()}...`}
                            className="h-8 text-xs pl-8 bg-slate-800/50 border-slate-700 focus:border-primary"
                        />
                    </div>
                </div>

                {/* Item list */}
                <div className="flex-1 overflow-y-auto min-h-0 px-3 py-2 space-y-0.5" style={{ maxHeight: '360px' }}>
                    {currentItems.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-10 text-slate-500">
                            <ActiveIcon className="h-8 w-8 mb-2 opacity-30" />
                            <p className="text-xs">{search ? 'No matching items' : 'No items available'}</p>
                        </div>
                    ) : (
                        currentItems.map(item => {
                            const isSelected = selKind === activeTab && selId === item.id;
                            return (
                                <button
                                    key={item.id}
                                    onClick={() => toggleSelect(item.id)}
                                    className={cn(
                                        "w-full text-left px-3 py-2 rounded-md flex items-center gap-2.5 transition-all duration-100 select-none cursor-pointer",
                                        isSelected ? activeCfg.selectedBorder : "hover:bg-slate-800/70 border border-transparent"
                                    )}
                                >
                                    <div className={cn(
                                        "h-4 w-4 rounded-full border shrink-0 flex items-center justify-center transition-colors",
                                        isSelected ? `${activeCfg.selectedBg} border-transparent` : "border-slate-600 bg-slate-800"
                                    )}>
                                        {isSelected && <CheckCircle className="h-3 w-3 text-white" />}
                                    </div>
                                    <ActiveIcon className={cn("h-3.5 w-3.5 shrink-0", activeCfg.color)} />
                                    <span className={cn("text-sm truncate flex-1", isSelected ? "text-white" : "text-slate-300")}>
                                        {item.label}
                                    </span>
                                    {item.sub && (
                                        <span className="text-[10px] text-slate-500 shrink-0 uppercase tracking-wide">{item.sub}</span>
                                    )}
                                </button>
                            );
                        })
                    )}
                </div>

                {/* Footer */}
                <DialogFooter className="flex items-center justify-between sm:justify-between px-4 py-2 border-t border-slate-800/60">
                    <span className="text-xs text-slate-500 truncate max-w-[240px]">
                        {selectedLabel ? <>Linking to <span className="text-slate-300">{selectedLabel}</span></> : 'Not linked (engagement attachment)'}
                    </span>
                    <div className="flex gap-2">
                        <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => onOpenChange(false)}>Cancel</Button>
                        <Button className="bg-primary hover:bg-primary/90 text-white" onClick={handleApply} disabled={isApplying}>
                            {isApplying ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Saving...</> : 'Save'}
                        </Button>
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
