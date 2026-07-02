/**
 * search/page.tsx — Advanced Global Search Page
 *
 * Features:
 *  - Boolean query input with live syntax-highlighted token display
 *  - Dork-style field scoping: severity:, status:, type:, cat:, engagement:, client:
 *  - Category scoping: finding:, asset:, testcase:, engagement:, client:, vault:
 *  - Quoted phrase matching: "SQL injection"
 *  - Quick Filter chip buttons that append clauses to the query
 *  - Autocomplete dropdown for dork field values
 *  - Recent searches (persisted in localStorage)
 *  - Sort toggle: Relevance vs. Updated
 *  - Match-count badge on each result
 *  - Syntax cheat-sheet help panel
 *  - Collapsible category sections
 *  - Preview modal with highlighted matched fields
 */
'use client';

import { useSearchParams, useRouter } from 'next/navigation';
import { useState, useEffect, useRef, useCallback, useMemo, Suspense } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { useGlobalSearch, SearchResultCategory, SearchResultItem } from '@/lib/hooks/use-search';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import {
    Search, Loader2, Briefcase, AlertTriangle, Monitor, ClipboardCheck,
    Building2, Lock, ArrowRight, FileQuestion, ExternalLink, ChevronDown,
    BookOpen, Clock, X, Zap, SortAsc, SortDesc, Sparkles, HelpCircle, ChevronRight, Tag,
} from 'lucide-react';
import Link from 'next/link';

// ── category metadata ────────────────────────────────────────────────────

const categoryMeta: Record<string, { label: string; singularLabel: string; icon: any; color: string; borderColor: string }> = {
    engagements: { label: 'Engagements', singularLabel: 'Engagement', icon: Briefcase, color: 'text-purple-400', borderColor: 'border-purple-500/20' },
    findings:    { label: 'Findings',    singularLabel: 'Finding',    icon: AlertTriangle, color: 'text-red-400',    borderColor: 'border-red-500/20' },
    assets:      { label: 'Assets',      singularLabel: 'Asset',      icon: Monitor,       color: 'text-cyan-400',   borderColor: 'border-cyan-500/20' },
    testcases:   { label: 'Test Cases',  singularLabel: 'Test Case',  icon: ClipboardCheck, color: 'text-amber-400', borderColor: 'border-amber-500/20' },
    clients:     { label: 'Clients',     singularLabel: 'Client',     icon: Building2,     color: 'text-emerald-400', borderColor: 'border-emerald-500/20' },
    vault:       { label: 'Vault Items', singularLabel: 'Vault Item', icon: Lock,          color: 'text-orange-400', borderColor: 'border-orange-500/20' },
};

// ── query tokenizer for live highlighting ────────────────────────────────

type TokenKind = 'keyword' | 'operator' | 'not' | 'dork-field' | 'dork-value' | 'quoted' | 'paren' | 'plain';
interface DisplayToken { kind: TokenKind; text: string }

function tokenizeForDisplay(query: string): DisplayToken[] {
    const tokens: DisplayToken[] = [];
    const re = /(\bAND\b|\bOR\b|\bNOT\b|[()"]|(?:severity|status|type|cat|engagement|client|finding|asset|testcase|vault|client):[^\s)]*|"[^"]*"|\S+)/gi;
    let m;
    let lastIndex = 0;
    while ((m = re.exec(query)) !== null) {
        if (m.index > lastIndex) {
            tokens.push({ kind: 'plain', text: query.slice(lastIndex, m.index) });
        }
        const w = m[0];
        const uw = w.toUpperCase();
        if (uw === 'AND' || uw === 'OR') tokens.push({ kind: 'operator', text: w });
        else if (uw === 'NOT') tokens.push({ kind: 'not', text: w });
        else if (w === '(' || w === ')') tokens.push({ kind: 'paren', text: w });
        else if (w.startsWith('"')) tokens.push({ kind: 'quoted', text: w });
        else if (/^(severity|status|type|cat|engagement|client|finding|asset|testcase|vault):/i.test(w)) {
            const colonIdx = w.indexOf(':');
            tokens.push({ kind: 'dork-field', text: w.slice(0, colonIdx + 1) });
            tokens.push({ kind: 'dork-value', text: w.slice(colonIdx + 1) });
        }
        else tokens.push({ kind: 'plain', text: w });
        lastIndex = m.index + m[0].length;
    }
    if (lastIndex < query.length) {
        tokens.push({ kind: 'plain', text: query.slice(lastIndex) });
    }
    return tokens;
}

const TOKEN_COLORS: Record<TokenKind, string> = {
    keyword:     'text-amber-300',
    operator:    'text-amber-400 font-bold',
    not:         'text-rose-400 font-bold',
    'dork-field':'text-violet-400',
    'dork-value':'text-cyan-300',
    quoted:      'text-emerald-300',
    paren:       'text-slate-400',
    plain:       'text-white',
};

// ── autocomplete config ──────────────────────────────────────────────────

const AUTOCOMPLETE_MAP: Record<string, string[]> = {
    'severity:': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'],
    'status:':   ['OPEN', 'IN_REVIEW', 'VERIFIED', 'REMEDIATED', 'CLOSED', 'active', 'completed', 'archived'],
    'type:':     ['web', 'network', 'mobile', 'api', 'cloud', 'iot', 'host', 'service'],
    'cat:':      ['injection', 'xss', 'ssrf', 'auth', 'csrf', 'rce', 'idor', 'disclosure', 'misconfig'],
};

const DORK_PREFIXES = [
    'severity:', 'status:', 'type:', 'cat:', 'engagement:', 'client:',
    'finding:', 'asset:', 'testcase:', 'vault:',
];

// ── quick filters ────────────────────────────────────────────────────────

interface QuickFilter { label: string; snippet: string; color: string }
const QUICK_FILTERS: QuickFilter[] = [
    { label: 'Critical Findings', snippet: 'finding: severity:CRITICAL', color: 'text-rose-400 border-rose-500/30 hover:bg-rose-500/10' },
    { label: 'High Findings',     snippet: 'finding: severity:HIGH',     color: 'text-orange-400 border-orange-500/30 hover:bg-orange-500/10' },
    { label: 'Open Issues',       snippet: 'status:OPEN',                color: 'text-amber-400 border-amber-500/30 hover:bg-amber-500/10' },
    { label: 'Verified',          snippet: 'status:VERIFIED',            color: 'text-blue-400 border-blue-500/30 hover:bg-blue-500/10' },
    { label: 'Remediated',        snippet: 'status:REMEDIATED',          color: 'text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10' },
    { label: 'Web Apps',          snippet: 'type:web',                   color: 'text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/10' },
    { label: 'SQL Topics',        snippet: 'cat:injection',              color: 'text-violet-400 border-violet-500/30 hover:bg-violet-500/10' },
    { label: 'XSS Topics',        snippet: 'cat:xss',                   color: 'text-pink-400 border-pink-500/30 hover:bg-pink-500/10' },
];

// ── example queries ──────────────────────────────────────────────────────

const EXAMPLE_QUERIES = [
    { label: 'Critical open findings', query: 'severity:CRITICAL AND status:OPEN' },
    { label: 'SQL injection findings', query: '"SQL injection" OR cat:injection' },
    { label: 'High/critical on web apps', query: '(severity:CRITICAL OR severity:HIGH) AND type:web' },
    { label: 'SSRF not remediated', query: 'SSRF NOT status:REMEDIATED' },
    { label: 'All assets for engagement', query: 'asset: engagement:acme' },
    { label: 'Vault items', query: 'vault:' },
];

// ── recent searches ──────────────────────────────────────────────────────

const RECENT_KEY = 'rw_recent_searches';
const MAX_RECENT = 8;

function getRecent(): string[] {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
}
function addRecent(q: string) {
    const prev = getRecent().filter(x => x !== q);
    localStorage.setItem(RECENT_KEY, JSON.stringify([q, ...prev].slice(0, MAX_RECENT)));
}
function removeRecent(q: string) {
    localStorage.setItem(RECENT_KEY, JSON.stringify(getRecent().filter(x => x !== q)));
}

// ── syntax highlighted display line ─────────────────────────────────────

function TokenizedLine({ query }: { query: string }) {
    const tokens = tokenizeForDisplay(query);
    return (
        <span className="font-mono text-sm">
            {tokens.map((tok, i) => (
                <span key={i} className={TOKEN_COLORS[tok.kind]}>{tok.text}</span>
            ))}
        </span>
    );
}

// ── multi-term highlight ─────────────────────────────────────────────────

function HighlightedText({ text, terms }: { text: string; terms: string[] }) {
    if (!text) return <>{text}</>;
    const validTerms = terms.filter(Boolean);
    if (!validTerms.length) return <>{text}</>;

    // Build a combined pattern from all terms
    const escaped = validTerms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');
    const parts = text.split(pattern);

    return (
        <>
            {parts.map((p, i) =>
                pattern.test(p) ? (
                    <mark key={i} className="bg-primary/30 text-primary rounded px-0.5">{p}</mark>
                ) : (
                    <span key={i}>{p}</span>
                )
            )}
        </>
    );
}

// ── result item ──────────────────────────────────────────────────────────

function ResultItem({ item, terms, onPreview }: {
    item: SearchResultItem;
    terms: string[];
    onPreview: () => void;
}) {
    return (
        <div className="flex items-center px-4 py-3 hover:bg-slate-800/60 transition-colors rounded-lg group">
            <button onClick={onPreview} className="flex-1 min-w-0 text-left cursor-pointer">
                <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white truncate group-hover:text-primary/80 transition-colors">
                        <HighlightedText text={item.title} terms={terms} />
                    </p>
                    {(item.match_count ?? 0) > 0 && (
                        <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/15 text-primary border border-primary/20">
                            {item.match_count} field{item.match_count !== 1 ? 's' : ''}
                        </span>
                    )}
                </div>
                <p className="text-xs text-slate-400 truncate mt-0.5">
                    <HighlightedText text={item.subtitle} terms={terms} />
                    {item.engagement_name && (
                        <span className="text-slate-500"> — {item.engagement_name}</span>
                    )}
                </p>
            </button>
            <div className="flex items-center gap-2 ml-3 shrink-0">
                {item.status && (
                    <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                        {item.status}
                    </Badge>
                )}
                <Link href={item.url} title="Go to item">
                    <div className="p-1.5 rounded hover:bg-primary/20 transition-colors">
                        <ArrowRight className="h-3.5 w-3.5 text-slate-600 group-hover:text-primary transition-colors" />
                    </div>
                </Link>
            </div>
        </div>
    );
}

// ── category section ─────────────────────────────────────────────────────

function CategorySection({ cat, terms, onPreview }: {
    cat: SearchResultCategory;
    terms: string[];
    onPreview: (item: SearchResultItem, category: string) => void;
}) {
    const meta = categoryMeta[cat.category] || { label: cat.category, singularLabel: cat.category, icon: FileQuestion, color: 'text-slate-400', borderColor: 'border-slate-700' };
    const Icon = meta.icon;
    const [expanded, setExpanded] = useState(true);

    return (
        <div className={`rounded-xl border ${meta.borderColor} bg-slate-900/50 overflow-hidden`}>
            <button
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-2.5 px-4 py-3 w-full text-left hover:bg-slate-800/40 transition-colors"
            >
                <div className={`h-7 w-7 rounded-lg flex items-center justify-center bg-slate-800`}>
                    <Icon className={`h-4 w-4 ${meta.color}`} />
                </div>
                <h3 className="text-sm font-semibold text-white flex-1">{meta.label}</h3>
                <Badge variant="secondary" className="bg-slate-800 text-slate-400 text-[10px]">
                    {cat.items.length} result{cat.items.length !== 1 ? 's' : ''}
                </Badge>
                <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform duration-200 ${expanded ? '' : '-rotate-90'}`} />
            </button>
            {expanded && (
                <div className="border-t border-slate-800/60 divide-y divide-slate-800/40">
                    {cat.items.map((item) => (
                        <ResultItem
                            key={item.id}
                            item={item}
                            terms={terms}
                            onPreview={() => onPreview(item, cat.category)}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ── preview modal ────────────────────────────────────────────────────────

function PreviewModal({ item, category, terms, open, onClose }: {
    item: SearchResultItem | null;
    category: string | null;
    terms: string[];
    open: boolean;
    onClose: () => void;
}) {
    if (!item || !category) return null;
    const meta = categoryMeta[category] || { label: category, singularLabel: category, icon: FileQuestion, color: 'text-slate-400', borderColor: '' };
    const Icon = meta.icon;

    const allFields = item.fields || {};
    const displayFields = terms.length
        ? Object.entries(allFields).filter(([, v]) => v && terms.some(t => v.toLowerCase().includes(t))).concat(
            Object.entries(allFields).filter(([k, v]) => v && !terms.some(t => v.toLowerCase().includes(t)))
        )
        : Object.entries(allFields).filter(([, v]) => !!v);

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="sm:max-w-lg bg-slate-900 border-slate-800">
                <DialogHeader>
                    <div className="flex items-center gap-2 mb-1">
                        <Icon className={`h-4 w-4 ${meta.color}`} />
                        <span className="text-xs text-slate-500 uppercase tracking-wider">{meta.singularLabel}</span>
                        {item.status && (
                            <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400 ml-auto">
                                {item.status}
                            </Badge>
                        )}
                    </div>
                    <DialogTitle className="text-white text-lg">
                        <HighlightedText text={item.title} terms={terms} />
                    </DialogTitle>
                    <p className="text-sm text-slate-400">
                        <HighlightedText text={item.subtitle} terms={terms} />
                    </p>
                    {item.engagement_name && (
                        <p className="text-xs text-slate-500 mt-0.5">Engagement: {item.engagement_name}</p>
                    )}
                </DialogHeader>

                <div className="space-y-3 my-2 max-h-[50vh] overflow-y-auto">
                    {displayFields.length > 0 ? displayFields.map(([key, value]) => (
                        <div key={key}>
                            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{key}</h4>
                            <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
                                <HighlightedText text={value} terms={terms} />
                            </p>
                        </div>
                    )) : (
                        <p className="text-sm text-slate-500 italic">No matching fields to display.</p>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="ghost" onClick={onClose} className="text-slate-400">Close</Button>
                    <Button asChild className="bg-primary hover:bg-primary/90">
                        <Link href={item.url} className="flex items-center gap-2">
                            <ExternalLink className="h-4 w-4" />
                            Go to {meta.singularLabel}
                        </Link>
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ── syntax help panel ────────────────────────────────────────────────────

function SyntaxHelp() {
    const [open, setOpen] = useState(false);
    return (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden">
            <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-2 px-4 py-3 w-full text-left hover:bg-slate-800/40 transition-colors"
            >
                <HelpCircle className="h-4 w-4 text-slate-500" />
                <span className="text-sm text-slate-400 font-medium flex-1">Search Syntax Reference</span>
                <ChevronDown className={`h-4 w-4 text-slate-600 transition-transform ${open ? '' : '-rotate-90'}`} />
            </button>
            {open && (
                <div className="border-t border-slate-800 p-4 grid grid-cols-1 sm:grid-cols-2 gap-6 text-xs">
                    <div>
                        <h4 className="text-slate-300 font-semibold mb-2 uppercase tracking-wider text-[10px]">Boolean Operators</h4>
                        <table className="w-full border-collapse">
                            <tbody className="divide-y divide-slate-800/50">
                                {[
                                    ['SSRF AND severity:HIGH', 'Both conditions'],
                                    ['XSS OR CSRF', 'Either condition'],
                                    ['SSRF NOT remediated', 'Exclude term'],
                                    ['(A OR B) AND C', 'Grouping with parens'],
                                ].map(([ex, desc]) => (
                                    <tr key={ex}>
                                        <td className="pr-3 py-1.5 font-mono text-violet-300 whitespace-nowrap">{ex}</td>
                                        <td className="py-1.5 text-slate-500">{desc}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div>
                        <h4 className="text-slate-300 font-semibold mb-2 uppercase tracking-wider text-[10px]">Field Dorks</h4>
                        <table className="w-full border-collapse">
                            <tbody className="divide-y divide-slate-800/50">
                                {[
                                    ['severity:HIGH', 'Filter by severity'],
                                    ['status:OPEN', 'Filter by status'],
                                    ['type:web', 'Filter by asset/engagement type'],
                                    ['cat:injection', 'Filter by category'],
                                    ['engagement:acme', 'Scope to engagement name'],
                                    ['client:corp', 'Scope to client name'],
                                ].map(([ex, desc]) => (
                                    <tr key={ex}>
                                        <td className="pr-3 py-1.5 font-mono text-cyan-300 whitespace-nowrap">{ex}</td>
                                        <td className="py-1.5 text-slate-500">{desc}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div>
                        <h4 className="text-slate-300 font-semibold mb-2 uppercase tracking-wider text-[10px]">Category Scoping</h4>
                        <table className="w-full border-collapse">
                            <tbody className="divide-y divide-slate-800/50">
                                {[
                                    ['finding:SSRF', 'Findings only'],
                                    ['asset:192.168', 'Assets only'],
                                    ['testcase:sql', 'Test cases only'],
                                    ['engagement:pen', 'Engagements only'],
                                    ['vault:', 'All vault items'],
                                ].map(([ex, desc]) => (
                                    <tr key={ex}>
                                        <td className="pr-3 py-1.5 font-mono text-emerald-300 whitespace-nowrap">{ex}</td>
                                        <td className="py-1.5 text-slate-500">{desc}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div>
                        <h4 className="text-slate-300 font-semibold mb-2 uppercase tracking-wider text-[10px]">Phrases & Misc</h4>
                        <table className="w-full border-collapse">
                            <tbody className="divide-y divide-slate-800/50">
                                {[
                                    ['"SQL injection"', 'Exact phrase match'],
                                    ['term1 term2', 'Implicit AND'],
                                    ['finding: severity:CRITICAL', 'Combine scoping + field'],
                                ].map(([ex, desc]) => (
                                    <tr key={ex}>
                                        <td className="pr-3 py-1.5 font-mono text-amber-300 whitespace-nowrap">{ex}</td>
                                        <td className="py-1.5 text-slate-500">{desc}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── advanced search input ────────────────────────────────────────────────

function SearchInput({ value, onChange, onSubmit, isLoading }: {
    value: string;
    onChange: (v: string) => void;
    onSubmit: () => void;
    isLoading: boolean;
}) {
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const [focused, setFocused] = useState(false);
    const [recent, setRecent] = useState<string[]>([]);
    const [acSuggestions, setAcSuggestions] = useState<string[]>([]);
    const [acPrefix, setAcPrefix] = useState('');
    const showRecent = focused && !value.trim() && recent.length > 0;

    useEffect(() => {
        setRecent(getRecent());
    }, [focused]);

    // Compute autocomplete hints based on the last token
    useEffect(() => {
        const lastToken = value.split(/\s+/).pop() || '';
        // Check if last token is a recognized dork field waiting for value
        for (const prefix of Object.keys(AUTOCOMPLETE_MAP)) {
            if (lastToken.toLowerCase().startsWith(prefix)) {
                const typed = lastToken.slice(prefix.length).toLowerCase();
                const opts = AUTOCOMPLETE_MAP[prefix].filter(o => o.toLowerCase().startsWith(typed));
                setAcSuggestions(opts);
                setAcPrefix(prefix);
                return;
            }
        }
        // Check if user is mid-typing a dork prefix
        const matchingPrefixes = DORK_PREFIXES.filter(p => p.toLowerCase().startsWith(lastToken.toLowerCase()) && lastToken.length > 0 && lastToken !== p);
        if (matchingPrefixes.length) {
            setAcSuggestions(matchingPrefixes);
            setAcPrefix('');
            return;
        }
        setAcSuggestions([]);
        setAcPrefix('');
    }, [value]);

    const applyAc = (suggestion: string) => {
        const parts = value.split(/\s+/);
        const last = parts[parts.length - 1];
        if (acPrefix) {
            // Replace the last token's value part
            parts[parts.length - 1] = acPrefix + suggestion + ' ';
        } else {
            // Replace the last partial prefix token
            parts[parts.length - 1] = suggestion;
        }
        onChange(parts.join(' '));
        inputRef.current?.focus();
        setAcSuggestions([]);
    };

    const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
        }
        if (e.key === 'Escape') setAcSuggestions([]);
    };

    return (
        <div className="relative">
            {/* Highlighted overlay (visible behind the transparent textarea) */}
            <div
                className="absolute inset-0 px-10 py-3 pointer-events-none whitespace-pre-wrap break-words font-mono text-sm leading-relaxed overflow-hidden"
                aria-hidden
            >
                <TokenizedLine query={value} />
                {/* invisible spacer to prevent layout shift */}
                {!value && <span className="text-slate-600">Search...</span>}
            </div>

            {/* Real textarea (transparent text so overlay shows through) */}
            <div className="relative">
                <Search className="absolute left-3 top-3.5 h-4 w-4 text-slate-500 z-10 pointer-events-none" />
                <textarea
                    ref={inputRef}
                    rows={1}
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    onKeyDown={handleKey}
                    onFocus={() => setFocused(true)}
                    onBlur={() => setTimeout(() => setFocused(false), 150)}
                    placeholder="Type to search... e.g. severity:HIGH AND status:OPEN"
                    className="w-full pl-10 pr-10 py-3 bg-slate-900/80 border border-slate-700 rounded-xl font-mono text-sm text-transparent caret-white focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 resize-none leading-relaxed transition-all placeholder:text-slate-600 placeholder:font-sans"
                    style={{ caretColor: 'white' }}
                    spellCheck={false}
                    autoFocus
                />
                <div className="absolute right-3 top-3 flex items-center gap-1.5">
                    {value && (
                        <button onClick={() => onChange('')} className="text-slate-600 hover:text-slate-400 transition-colors">
                            <X className="h-4 w-4" />
                        </button>
                    )}
                    {isLoading ? (
                        <Loader2 className="h-4 w-4 text-primary animate-spin" />
                    ) : (
                        <Sparkles className="h-4 w-4 text-slate-700" />
                    )}
                </div>
            </div>

            {/* Recent searches dropdown */}
            {showRecent && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                    <div className="px-3 py-2 border-b border-slate-800 flex items-center gap-1.5">
                        <Clock className="h-3 w-3 text-slate-500" />
                        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Recent Searches</span>
                    </div>
                    {recent.map(r => (
                        <div key={r} className="flex items-center group hover:bg-slate-800/60 transition-colors">
                            <button
                                onClick={() => { onChange(r); onSubmit(); }}
                                className="flex-1 text-left px-3 py-2 text-sm font-mono text-slate-300"
                            >
                                <TokenizedLine query={r} />
                            </button>
                            <button
                                onClick={() => { removeRecent(r); setRecent(getRecent()); }}
                                className="px-3 py-2 text-slate-700 hover:text-slate-400 opacity-0 group-hover:opacity-100 transition-all"
                            >
                                <X className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Autocomplete dropdown */}
            {acSuggestions.length > 0 && focused && value && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                    <div className="px-3 py-2 border-b border-slate-800 flex items-center gap-1.5">
                        <Zap className="h-3 w-3 text-violet-400" />
                        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Suggestions</span>
                    </div>
                    {acSuggestions.map(s => (
                        <button
                            key={s}
                            onClick={() => applyAc(s)}
                            className="flex items-center gap-2 w-full text-left px-3 py-2 hover:bg-slate-800/60 transition-colors text-sm font-mono"
                        >
                            <span className="text-violet-400">{acPrefix}</span>
                            <span className="text-cyan-300">{s}</span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

// ── main page ────────────────────────────────────────────────────────────

function SearchPageContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const urlQuery = searchParams?.get('q') || '';
    const [localQuery, setLocalQuery] = useState(urlQuery);
    const [sort, setSort] = useState<'relevance' | 'updated'>('relevance');
    const [previewItem, setPreviewItem] = useState<SearchResultItem | null>(null);
    const [previewCategory, setPreviewCategory] = useState<string | null>(null);

    useEffect(() => { setLocalQuery(urlQuery); }, [urlQuery]);

    const { data, isLoading, isFetching } = useGlobalSearch(urlQuery, sort);

    const terms = data?.parsed_terms || [];
    const totalResults = data?.total ?? 0;

    const commit = useCallback(() => {
        const q = localQuery.trim();
        if (q) {
            addRecent(q);
            router.push(`/search?q=${encodeURIComponent(q)}`);
        }
    }, [localQuery, router]);

    const applyFilter = (snippet: string) => {
        const newQ = localQuery.trim() ? `${localQuery.trim()} AND ${snippet}` : snippet;
        setLocalQuery(newQ);
        addRecent(newQ);
        router.push(`/search?q=${encodeURIComponent(newQ)}`);
    };

    const applyExample = (q: string) => {
        setLocalQuery(q);
        addRecent(q);
        router.push(`/search?q=${encodeURIComponent(q)}`);
    };

    return (
        <DashboardLayout>
            <div className="p-6 max-w-5xl mx-auto space-y-5">
                {/* Header */}
                <div className="flex items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2.5 mb-1">
                            <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-purple-500/20 to-violet-500/20 border border-primary/20 flex items-center justify-center">
                                <Search className="h-4.5 w-4.5 text-primary" />
                            </div>
                            <h1 className="text-2xl font-bold text-white">Advanced Search</h1>
                        </div>
                        <p className="text-sm text-slate-400 ml-11">
                            Boolean operators · Field dorks · Quoted phrases · Cross-resource search
                        </p>
                    </div>
                    {urlQuery && !isLoading && data && (
                        <div className="text-right shrink-0">
                            <p className="text-lg font-bold text-white">{totalResults}</p>
                            <p className="text-xs text-slate-500">results</p>
                        </div>
                    )}
                </div>

                {/* Search Input */}
                <SearchInput
                    value={localQuery}
                    onChange={setLocalQuery}
                    onSubmit={commit}
                    isLoading={isFetching}
                />

                {/* Active query display + sort */}
                {urlQuery && (
                    <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 text-xs text-slate-500 min-w-0">
                            <span className="shrink-0">Searching:</span>
                            <span className="font-mono truncate text-slate-300 bg-slate-800/60 px-2 py-0.5 rounded">
                                <TokenizedLine query={urlQuery} />
                            </span>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                            <button
                                onClick={() => setSort('relevance')}
                                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs transition-colors ${sort === 'relevance' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-slate-500 hover:text-white'}`}
                            >
                                <Sparkles className="h-3 w-3" /> Relevance
                            </button>
                            <button
                                onClick={() => setSort('updated')}
                                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs transition-colors ${sort === 'updated' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-slate-500 hover:text-white'}`}
                            >
                                <Clock className="h-3 w-3" /> Recent
                            </button>
                        </div>
                    </div>
                )}

                {/* Quick Filters */}
                {!urlQuery && (
                    <div>
                        <p className="text-xs text-slate-500 mb-2 flex items-center gap-1.5">
                            <Tag className="h-3.5 w-3.5" /> Quick Filters
                        </p>
                        <div className="flex flex-wrap gap-2">
                            {QUICK_FILTERS.map(f => (
                                <button
                                    key={f.snippet}
                                    onClick={() => applyFilter(f.snippet)}
                                    className={`text-xs px-3 py-1.5 rounded-full border bg-slate-800/50 ${f.color} transition-all font-medium`}
                                >
                                    {f.label}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Loading */}
                {isLoading && urlQuery && (
                    <div className="flex justify-center py-16">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                )}

                {/* Results */}
                {data?.results && data.results.length > 0 && (
                    <div className="space-y-3">
                        {data.results.map(cat => (
                            <CategorySection
                                key={cat.category}
                                cat={cat}
                                terms={terms}
                                onPreview={(item, category) => { setPreviewItem(item); setPreviewCategory(category); }}
                            />
                        ))}
                    </div>
                )}

                {/* No Results */}
                {data?.results && data.results.length === 0 && urlQuery && (
                    <div className="text-center py-16 space-y-3">
                        <FileQuestion className="h-12 w-12 text-slate-700 mx-auto" />
                        <p className="text-slate-400 text-sm">No results for <span className="font-mono text-primary">"{urlQuery}"</span></p>
                        <p className="text-slate-600 text-xs">Try different terms, boolean operators, or field dorks</p>
                        <div className="flex flex-wrap justify-center gap-2 mt-4">
                            {EXAMPLE_QUERIES.map(e => (
                                <button
                                    key={e.query}
                                    onClick={() => applyExample(e.query)}
                                    className="text-xs font-mono bg-slate-800 text-slate-400 hover:text-primary/80 hover:bg-slate-700 px-3 py-1.5 rounded-lg transition-colors border border-slate-700"
                                    title={e.label}
                                >
                                    {e.query}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Empty State */}
                {!urlQuery && (
                    <div className="space-y-5">
                        {/* Example queries */}
                        <div>
                            <p className="text-xs text-slate-500 mb-3 flex items-center gap-1.5">
                                <BookOpen className="h-3.5 w-3.5" /> Example Queries
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                {EXAMPLE_QUERIES.map(e => (
                                    <button
                                        key={e.query}
                                        onClick={() => applyExample(e.query)}
                                        className="flex items-center gap-3 px-4 py-3 rounded-xl border border-slate-800 bg-slate-900/40 hover:bg-slate-800/50 hover:border-primary/30 transition-all text-left group"
                                    >
                                        <ChevronRight className="h-3.5 w-3.5 text-slate-600 group-hover:text-primary shrink-0 transition-colors" />
                                        <div>
                                            <p className="text-xs text-slate-500 mb-0.5">{e.label}</p>
                                            <p className="text-xs font-mono text-slate-300 group-hover:text-primary/80 transition-colors">{e.query}</p>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Syntax help */}
                        <SyntaxHelp />
                    </div>
                )}

                {/* Syntax help also shown when there are results */}
                {data?.results && data.results.length > 0 && (
                    <SyntaxHelp />
                )}

                <PreviewModal
                    item={previewItem}
                    category={previewCategory}
                    terms={terms}
                    open={!!previewItem}
                    onClose={() => { setPreviewItem(null); setPreviewCategory(null); }}
                />
            </div>
        </DashboardLayout>
    );
}

export default function SearchPage() {
    return (
        <Suspense fallback={
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        }>
            <SearchPageContent />
        </Suspense>
    );
}
