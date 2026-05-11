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
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    Search, Bug, Target, Server, Key, Trash2, Loader2, CheckCircle, Link as LinkIcon, Radar,
} from 'lucide-react';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useAssets } from '@/lib/hooks/use-assets';
import { useVaultItems } from '@/lib/hooks/use-vault';
import { useCleanupArtifacts } from '@/lib/hooks/use-cleanup-artifacts';
import { useIntelItems, useLinkIntel, useUnlinkIntel, useIntelByEntity } from '@/lib/hooks/use-intel';
import { useInfraItems, useLinkInfra, useUnlinkInfra, useInfraByEntity } from '@/lib/hooks/use-infra';
import { toast } from 'sonner';

export type EntityType = 'finding' | 'testcase' | 'asset' | 'vault' | 'cleanup';
export type LinkResourceType = 'findings' | 'testcases' | 'assets' | 'vault' | 'cleanup' | 'intel' | 'infra';

const ALL_TABS: { key: LinkResourceType; label: string; icon: React.ElementType; color: string; selectedBg: string; selectedBorder: string }[] = [
    { key: 'findings',  label: 'Findings',    icon: Bug,    color: 'text-red-400',     selectedBg: 'bg-red-500',     selectedBorder: 'border-red-500/30 bg-red-500/5'     },
    { key: 'testcases', label: 'Test Cases',  icon: Target, color: 'text-primary',  selectedBg: 'bg-primary',  selectedBorder: 'border-primary/30 bg-primary/5'},
    { key: 'assets',    label: 'Assets',      icon: Server, color: 'text-blue-400',    selectedBg: 'bg-blue-500',    selectedBorder: 'border-blue-500/30 bg-blue-500/5'   },
    { key: 'vault',     label: 'Vault',       icon: Key,    color: 'text-amber-400',   selectedBg: 'bg-amber-500',   selectedBorder: 'border-amber-500/30 bg-amber-500/5' },
    { key: 'cleanup',   label: 'Cleanup',     icon: Trash2, color: 'text-emerald-400', selectedBg: 'bg-emerald-500', selectedBorder: 'border-emerald-500/30 bg-emerald-500/5'},
    { key: 'intel',     label: 'Intel',       icon: Radar,  color: 'text-cyan-400',    selectedBg: 'bg-cyan-500',    selectedBorder: 'border-cyan-500/30 bg-cyan-500/5'   },
    { key: 'infra',     label: 'Infra',       icon: Server, color: 'text-orange-400',  selectedBg: 'bg-orange-500',  selectedBorder: 'border-orange-500/30 bg-orange-500/5'},
];

const EXCLUDED_TABS: Record<EntityType, LinkResourceType[]> = {
    finding:  ['findings'],
    testcase: ['testcases'],
    asset:    ['assets', 'intel', 'infra'],  // intel/infra API doesn't support asset entity type
    vault:    ['vault', 'intel', 'infra', 'cleanup'],   // vault items link to findings/testcases/assets only
    cleanup:  ['cleanup', 'intel', 'infra', 'vault'],   // cleanup artifacts link to findings/testcases/assets only
};

const intelTypeColors: Record<string, string> = {
    CVE: 'bg-red-500/15 text-red-400 border-red-500/30',
    ADVISORY: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    ARTICLE: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    EXPLOIT: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    ZINE: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    OTHER: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
};

export interface LinkedIdMap {
    findings:  Set<string>;
    testcases: Set<string>;
    assets:    Set<string>;
    vault:     Set<string>;
    cleanup:   Set<string>;
    intel:     Set<string>;
    infra:     Set<string>;
}

interface LinkEntityDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    engagementId: string;
    entityType: EntityType;
    entityId: string;
    entityName: string;
    linkedIds: LinkedIdMap;
    onLink: (type: LinkResourceType, id: string) => Promise<void>;
    onUnlink: (type: LinkResourceType, id: string) => Promise<void>;
    /** Optional whitelist of resource tabs to show. When provided, replaces
     *  the default EXCLUDED_TABS behavior — only tabs in this list render. */
    allowedTypes?: LinkResourceType[];
}

export function LinkEntityDialog({
    open,
    onOpenChange,
    engagementId,
    entityType,
    entityId,
    entityName,
    linkedIds,
    onLink,
    onUnlink,
    allowedTypes,
}: LinkEntityDialogProps) {
    const excluded = allowedTypes
        ? ALL_TABS.map(t => t.key).filter(k => !allowedTypes.includes(k))
        : EXCLUDED_TABS[entityType];
    const TABS = ALL_TABS.filter(t => !excluded.includes(t.key));

    const [activeTab, setActiveTab] = useState<LinkResourceType>(TABS[0]?.key ?? 'findings');
    const [search, setSearch] = useState('');
    const [selectionMap, setSelectionMap] = useState<Record<LinkResourceType, Set<string>>>({
        findings: new Set(), testcases: new Set(), assets: new Set(),
        vault: new Set(), cleanup: new Set(), intel: new Set(), infra: new Set(),
    });
    const [lastClickedIndex, setLastClickedIndex] = useState<number | null>(null);
    const [isApplying, setIsApplying] = useState(false);

    // Data hooks
    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: assets = [] } = useAssets(engagementId);
    const { data: vaultItems = [] } = useVaultItems(engagementId);
    const { data: cleanupArtifacts = [] } = useCleanupArtifacts(engagementId);
    const { data: intelData } = useIntelItems({ limit: 200 });
    const intelItems = intelData?.items ?? [];
    // intel/infra hooks only support 'finding' | 'testcase' | 'note'.
    // For other entity types (asset/vault/cleanup) intel+infra are excluded
    // anyway via EXCLUDED_TABS, so we pass a compat-default to satisfy the
    // hook signature without firing real fetches (entityId is empty).
    const intelInfraCompat = (entityType === 'finding' || entityType === 'testcase')
        ? entityType
        : 'finding';
    const intelInfraId = (entityType === 'finding' || entityType === 'testcase') ? entityId : '';
    const { data: linkedIntelItems = [] } = useIntelByEntity(intelInfraCompat as any, intelInfraId);
    const linkIntel = useLinkIntel();
    const unlinkIntel = useUnlinkIntel();
    const { data: infraData } = useInfraItems({ limit: 200 });
    const infraItems = infraData?.items ?? [];
    const { data: linkedInfraItems = [] } = useInfraByEntity(intelInfraCompat as any, intelInfraId);
    const linkInfra = useLinkInfra();
    const unlinkInfra = useUnlinkInfra();

    // Normalize items for each tab
    const items = useMemo(() => {
        const term = search.toLowerCase();
        const filter = (list: { id: string; label: string; sub?: string }[]) =>
            list.filter(i => i.label.toLowerCase().includes(term));

        return {
            findings:  filter(findings.map(f => ({ id: f.id, label: f.title, sub: f.severity }))),
            testcases: filter(testcases.map(t => ({ id: t.id, label: t.title, sub: t.category || undefined }))),
            assets:    filter(assets.map(a => ({ id: a.id, label: a.name, sub: a.asset_type }))),
            vault:     filter(vaultItems.map(v => ({ id: v.id, label: v.name, sub: v.item_type }))),
            cleanup:   filter(cleanupArtifacts.map(c => ({ id: c.id, label: c.title, sub: c.artifact_type }))),
            intel:     filter(intelItems.map(i => ({ id: i.id, label: i.title, sub: i.cve_id || i.item_type }))),
            infra:     filter(infraItems.map(i => ({ id: i.id, label: i.name, sub: i.infra_type }))),
        };
    }, [findings, testcases, assets, vaultItems, cleanupArtifacts, intelItems, infraItems, search]);

    // Pre-populate selections when opening
    useEffect(() => {
        if (open) {
            setSelectionMap({
                findings:  new Set(linkedIds.findings),
                testcases: new Set(linkedIds.testcases),
                assets:    new Set(linkedIds.assets),
                vault:     new Set(linkedIds.vault),
                cleanup:   new Set(linkedIds.cleanup),
                intel:     new Set(linkedIntelItems.map(i => i.id)),
                infra:     new Set(linkedInfraItems.map(i => i.id)),
            });
            setLastClickedIndex(null);
        }
    }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleSwitchTab = (tab: LinkResourceType) => {
        setActiveTab(tab);
        setSearch('');
        setLastClickedIndex(null);
    };

    const handleOpenChange = (v: boolean) => {
        if (!v) { setSearch(''); setActiveTab(TABS[0]?.key ?? 'findings'); }
        onOpenChange(v);
    };

    const handleToggleSelect = (itemId: string, index: number, shiftKey: boolean, filteredItems: { id: string }[]) => {
        setSelectionMap(prev => {
            const currentSet = new Set(prev[activeTab]);
            if (shiftKey && lastClickedIndex !== null) {
                const start = Math.min(lastClickedIndex, index);
                const end = Math.max(lastClickedIndex, index);
                const shouldSelect = !currentSet.has(itemId);
                for (let i = start; i <= end; i++) {
                    if (filteredItems[i]) {
                        if (shouldSelect) currentSet.add(filteredItems[i].id);
                        else currentSet.delete(filteredItems[i].id);
                    }
                }
            } else {
                if (currentSet.has(itemId)) currentSet.delete(itemId);
                else currentSet.add(itemId);
            }
            return { ...prev, [activeTab]: currentSet };
        });
        setLastClickedIndex(index);
    };

    const handleApply = async () => {
        setIsApplying(true);
        let linked = 0, unlinked = 0, errors = 0;

        // Standard types
        const standardTypes: LinkResourceType[] = ['findings', 'testcases', 'assets', 'vault', 'cleanup'];
        for (const type of standardTypes) {
            if (excluded.includes(type)) continue;
            const currentlyLinked = linkedIds[type];
            const selected = selectionMap[type];
            const toLink = [...selected].filter(id => !currentlyLinked.has(id));
            const toUnlink = [...currentlyLinked].filter(id => !selected.has(id));
            for (const resourceId of toLink) {
                try { await onLink(type, resourceId); linked++; } catch { errors++; }
            }
            for (const resourceId of toUnlink) {
                try { await onUnlink(type, resourceId); unlinked++; } catch { errors++; }
            }
        }

        // Intel
        if (!excluded.includes('intel')) {
            const currentLinkedIntel = new Set(linkedIntelItems.map(i => i.id));
            const selectedIntel = selectionMap.intel;
            for (const itemId of [...selectedIntel].filter(id => !currentLinkedIntel.has(id))) {
                try { await linkIntel.mutateAsync({ itemId, entityType, entityId }); linked++; } catch { errors++; }
            }
            for (const itemId of [...currentLinkedIntel].filter(id => !selectedIntel.has(id))) {
                try { await unlinkIntel.mutateAsync({ itemId, entityType, entityId }); unlinked++; } catch { errors++; }
            }
        }

        // Infra
        if (!excluded.includes('infra')) {
            const currentLinkedInfra = new Set(linkedInfraItems.map(i => i.id));
            const selectedInfra = selectionMap.infra;
            for (const itemId of [...selectedInfra].filter(id => !currentLinkedInfra.has(id))) {
                try { await linkInfra.mutateAsync({ itemId, entityType, entityId }); linked++; } catch { errors++; }
            }
            for (const itemId of [...currentLinkedInfra].filter(id => !selectedInfra.has(id))) {
                try { await unlinkInfra.mutateAsync({ itemId, entityType, entityId }); unlinked++; } catch { errors++; }
            }
        }

        if (linked > 0 || unlinked > 0 || errors > 0) {
            const parts: string[] = [];
            if (linked > 0) parts.push(`${linked} linked`);
            if (unlinked > 0) parts.push(`${unlinked} unlinked`);
            if (errors > 0) parts.push(`${errors} failed`);
            toast.success(`Links: ${parts.join(', ')}`);
        } else {
            toast.info('No changes to apply');
        }

        setIsApplying(false);
        onOpenChange(false);
    };

    const currentItems = items[activeTab] ?? [];
    const activeTabConfig = TABS.find(t => t.key === activeTab) ?? TABS[0];
    const ActiveIcon = activeTabConfig?.icon ?? Bug;
    const totalSelected = Object.values(selectionMap).reduce((sum, set) => sum + set.size, 0);

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[740px] p-0 gap-0 overflow-hidden max-h-[80vh] flex flex-col">
                <DialogHeader className="px-4 pt-4 pb-3 border-b border-slate-800/60">
                    <DialogTitle className="text-base font-semibold flex items-center gap-2">
                        <LinkIcon className="h-4 w-4 text-indigo-400" />
                        Link Items to &ldquo;{entityName}&rdquo;
                    </DialogTitle>
                    <p className="text-xs text-slate-500 mt-0.5">
                        Select items to link. Use <kbd className="px-1 py-0.5 bg-slate-700 rounded text-[10px] font-mono">Shift+Click</kbd> to select a range.
                    </p>
                </DialogHeader>

                {/* Tabs */}
                <div className="flex border-b border-slate-800/60 px-2 gap-0.5 overflow-x-auto" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                    {TABS.map(tab => {
                        const Icon = tab.icon;
                        return (
                            <button
                                key={tab.key}
                                onClick={() => handleSwitchTab(tab.key)}
                                className={cn(
                                    "flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-all border-b-2 -mb-px shrink-0 whitespace-nowrap",
                                    activeTab === tab.key
                                        ? "border-indigo-400 text-indigo-300"
                                        : "border-transparent text-slate-500 hover:text-slate-300"
                                )}
                            >
                                <Icon className={cn("h-3.5 w-3.5", activeTab === tab.key ? tab.color : "")} />
                                {tab.label}
                                {selectionMap[tab.key].size > 0 && (
                                    <Badge className={cn("h-4 px-1 text-[9px] border-none",
                                        activeTab === tab.key ? 'bg-indigo-500/20 text-indigo-400' : 'bg-slate-700/50 text-slate-400')}>
                                        {selectionMap[tab.key].size}
                                    </Badge>
                                )}
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
                            placeholder={`Search ${activeTabConfig?.label.toLowerCase() ?? ''}...`}
                            className="h-8 text-xs pl-8 bg-slate-800/50 border-slate-700 focus:border-primary"
                        />
                    </div>
                </div>

                {/* Item list */}
                <div className="flex-1 overflow-y-auto min-h-0 px-3 py-2 space-y-0.5" style={{ maxHeight: '400px' }}>
                    {currentItems.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-10 text-slate-500">
                            <ActiveIcon className="h-8 w-8 mb-2 opacity-30" />
                            <p className="text-xs">{search ? 'No matching items' : 'No items available'}</p>
                        </div>
                    ) : (
                        currentItems.map((item, idx) => {
                            const isSelected = selectionMap[activeTab].has(item.id);
                            return (
                                <button
                                    key={item.id}
                                    onClick={(e) => handleToggleSelect(item.id, idx, e.shiftKey, currentItems)}
                                    className={cn(
                                        "w-full text-left px-3 py-2 rounded-md flex items-center gap-2.5 transition-all duration-100 select-none cursor-pointer",
                                        isSelected
                                            ? activeTabConfig.selectedBorder
                                            : "hover:bg-slate-800/70 border border-transparent",
                                    )}
                                >
                                    <div className={cn(
                                        "h-4 w-4 rounded border shrink-0 flex items-center justify-center transition-colors",
                                        isSelected ? `${activeTabConfig.selectedBg} border-transparent` : "border-slate-600 bg-slate-800"
                                    )}>
                                        {isSelected && <CheckCircle className="h-3 w-3 text-white" />}
                                    </div>
                                    <ActiveIcon className={cn("h-3.5 w-3.5 shrink-0", activeTabConfig.color)} />
                                    <span className={cn("text-sm truncate flex-1", isSelected ? "text-white" : "text-slate-300")}>
                                        {item.label}
                                    </span>
                                    {item.sub && (
                                        <Badge variant="secondary" className={cn(
                                            "text-[10px] h-4 px-1.5 shrink-0",
                                            activeTab === 'intel'
                                                ? (intelTypeColors[item.sub.toUpperCase()] || intelTypeColors.OTHER)
                                                : "bg-slate-800 text-slate-400 border-slate-700"
                                        )}>
                                            {item.sub}
                                        </Badge>
                                    )}
                                </button>
                            );
                        })
                    )}
                </div>

                {/* Footer */}
                <DialogFooter className="flex items-center justify-between sm:justify-between px-4 py-2 border-t border-slate-800/60">
                    <span className="text-xs text-slate-500">{totalSelected} selected across all types</span>
                    <div className="flex gap-2">
                        <Button variant="outline" className="border-slate-700 text-slate-400 hover:text-white" onClick={() => handleOpenChange(false)}>Cancel</Button>
                        <Button className="bg-primary hover:bg-primary/90 text-white" onClick={handleApply} disabled={isApplying}>
                            {isApplying ? <><Loader2 className="h-4 w-4 animate-spin mr-1" /> Applying...</> : 'Apply All'}
                        </Button>
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
