/**
 * CVSS v3.1 Calculator Engine
 *
 * TypeScript port of FIRST.ORG's cvsscalc31.js (BSD-3-Clause License).
 * Original: https://www.first.org/cvss/calculator/cvsscalc31.js
 *
 * Copyright (c) 2019, FIRST.ORG, INC. All rights reserved.
 * Redistribution and use in source and binary forms, with or without modification,
 * are permitted provided that the conditions in the BSD-3-Clause license are met.
 */

// ─── Types ──────────────────────────────────────────────────────────────────

export type MetricKey = 'AV' | 'AC' | 'PR' | 'UI' | 'S' | 'C' | 'I' | 'A';

export interface CvssMetrics {
    AV: string; // Attack Vector:        N | A | L | P
    AC: string; // Attack Complexity:    L | H
    PR: string; // Privileges Required:  N | L | H
    UI: string; // User Interaction:     N | R
    S: string; // Scope:                U | C
    C: string; // Confidentiality:      N | L | H
    I: string; // Integrity:            N | L | H
    A: string; // Availability:         N | L | H
}

export interface CvssResult {
    success: true;
    baseMetricScore: string;
    baseSeverity: string;
    vectorString: string;
    baseISS: number;
    baseImpact: number;
    baseExploitability: number;
}

export interface CvssError {
    success: false;
    errorType: 'MissingBaseMetric' | 'UnknownMetricValue' | 'MalformedVectorString' | 'MultipleDefinitionsOfMetric';
    errorMetrics?: string[];
}

export type CvssCalcResult = CvssResult | CvssError;

// ─── Metric Definitions (for UI rendering) ──────────────────────────────────

export interface MetricOption {
    value: string;
    label: string;
    description: string;
}

export interface MetricDefinition {
    key: MetricKey;
    name: string;
    description: string;
    options: MetricOption[];
}

export const METRIC_DEFINITIONS: MetricDefinition[] = [
    {
        key: 'AV',
        name: 'Attack Vector',
        description: 'How can the vulnerability be exploited?',
        options: [
            { value: 'N', label: 'Network', description: 'Remotely exploitable; no physical or local access needed' },
            { value: 'A', label: 'Adjacent', description: 'Requires adjacent network access (e.g. same subnet, Bluetooth)' },
            { value: 'L', label: 'Local', description: 'Requires local access (e.g. keyboard, SSH session)' },
            { value: 'P', label: 'Physical', description: 'Requires physical access to the device' },
        ],
    },
    {
        key: 'AC',
        name: 'Attack Complexity',
        description: 'What conditions beyond attacker control must exist?',
        options: [
            { value: 'L', label: 'Low', description: 'No specialized conditions; reproducible at will' },
            { value: 'H', label: 'High', description: 'Success depends on conditions the attacker cannot control' },
        ],
    },
    {
        key: 'PR',
        name: 'Privileges Required',
        description: 'What level of privileges must an attacker possess?',
        options: [
            { value: 'N', label: 'None', description: 'No prior authentication needed' },
            { value: 'L', label: 'Low', description: 'Basic user privileges (e.g. standard user account)' },
            { value: 'H', label: 'High', description: 'Significant privileges (e.g. administrator)' },
        ],
    },
    {
        key: 'UI',
        name: 'User Interaction',
        description: 'Must a user take action for the exploit to succeed?',
        options: [
            { value: 'N', label: 'None', description: 'No user interaction required' },
            { value: 'R', label: 'Required', description: 'User must perform some action (e.g. click a link)' },
        ],
    },
    {
        key: 'S',
        name: 'Scope',
        description: 'Can the vulnerability impact resources beyond its security scope?',
        options: [
            { value: 'U', label: 'Unchanged', description: 'Impact limited to the vulnerable component' },
            { value: 'C', label: 'Changed', description: 'Can impact resources beyond the vulnerable component' },
        ],
    },
    {
        key: 'C',
        name: 'Confidentiality',
        description: 'Impact to the confidentiality of information resources',
        options: [
            { value: 'N', label: 'None', description: 'No loss of confidentiality' },
            { value: 'L', label: 'Low', description: 'Some loss of confidentiality; access to some restricted info' },
            { value: 'H', label: 'High', description: 'Total loss of confidentiality; all resources disclosed' },
        ],
    },
    {
        key: 'I',
        name: 'Integrity',
        description: 'Impact to the integrity of information resources',
        options: [
            { value: 'N', label: 'None', description: 'No loss of integrity' },
            { value: 'L', label: 'Low', description: 'Modification possible but limited in scope' },
            { value: 'H', label: 'High', description: 'Total loss of integrity; attacker can modify anything' },
        ],
    },
    {
        key: 'A',
        name: 'Availability',
        description: 'Impact to the availability of information resources',
        options: [
            { value: 'N', label: 'None', description: 'No impact to availability' },
            { value: 'L', label: 'Low', description: 'Reduced performance or partial denial of access' },
            { value: 'H', label: 'High', description: 'Total loss of availability; complete denial of service' },
        ],
    },
];

// ─── Weights (from CVSS 3.1 specification) ──────────────────────────────────

const Weight: Record<string, Record<string, number | Record<string, number>>> = {
    AV: { N: 0.85, A: 0.62, L: 0.55, P: 0.2 },
    AC: { H: 0.44, L: 0.77 },
    PR: {
        U: { N: 0.85, L: 0.62, H: 0.27 },  // Scope Unchanged
        C: { N: 0.85, L: 0.68, H: 0.50 },  // Scope Changed
    },
    UI: { N: 0.85, R: 0.62 },
    S: { U: 6.42, C: 7.52 },
    CIA: { N: 0, L: 0.22, H: 0.56 },
};

const EXPLOITABILITY_COEFFICIENT = 8.22;
const SCOPE_COEFFICIENT = 1.08;

// ─── Severity Ratings ───────────────────────────────────────────────────────

const severityRatings = [
    { name: 'None', bottom: 0.0, top: 0.0 },
    { name: 'Low', bottom: 0.1, top: 3.9 },
    { name: 'Medium', bottom: 4.0, top: 6.9 },
    { name: 'High', bottom: 7.0, top: 8.9 },
    { name: 'Critical', bottom: 9.0, top: 10.0 },
];

export function severityRating(score: number | string): string {
    const val = Number(score);
    if (isNaN(val)) return 'None';
    for (const r of severityRatings) {
        if (val >= r.bottom && val <= r.top) return r.name;
    }
    return 'None';
}

export function severityColor(severity: string): string {
    switch (severity) {
        case 'Critical': return '#ef4444'; // red-500
        case 'High': return '#f97316'; // orange-500
        case 'Medium': return '#f59e0b'; // amber-500
        case 'Low': return '#3b82f6'; // blue-500
        case 'None': return '#64748b'; // slate-500
        default: return '#64748b';
    }
}

// ─── Rounding (CVSS 3.1 spec: round up to 1 decimal place) ─────────────────

function roundUp1(input: number): number {
    const int_input = Math.round(input * 100000);
    if (int_input % 10000 === 0) {
        return int_input / 100000;
    } else {
        return (Math.floor(int_input / 10000) + 1) / 10;
    }
}

// ─── Vector String Regex ────────────────────────────────────────────────────

const CVSS_VERSION_ID = 'CVSS:3.1';
const vectorRegex = /^CVSS:3\.1\/(AV:[NALP]|AC:[LH]|PR:[NLH]|UI:[NR]|S:[UC]|[CIA]:[NLH])(\/(?:AV:[NALP]|AC:[LH]|PR:[NLH]|UI:[NR]|S:[UC]|[CIA]:[NLH])){0,7}$/;

// ─── Core Calculation ───────────────────────────────────────────────────────

export function calculateCVSSFromMetrics(metrics: CvssMetrics): CvssCalcResult {
    const { AV, AC, PR, UI, S, C, I, A } = metrics;

    // Validate all base metrics are defined
    const missing: string[] = [];
    if (!AV) missing.push('AV');
    if (!AC) missing.push('AC');
    if (!PR) missing.push('PR');
    if (!UI) missing.push('UI');
    if (!S) missing.push('S');
    if (!C) missing.push('C');
    if (!I) missing.push('I');
    if (!A) missing.push('A');

    if (missing.length > 0) {
        return { success: false, errorType: 'MissingBaseMetric', errorMetrics: missing };
    }

    // Validate metric values — use hasOwnProperty, NOT truthy checks,
    // because CIA 'None' has weight 0 which is falsy.
    const bad: string[] = [];
    const w = Weight;
    if (!(w.AV as Record<string, number>).hasOwnProperty(AV)) bad.push('AV');
    if (!(w.AC as Record<string, number>).hasOwnProperty(AC)) bad.push('AC');
    if (!((w.PR as Record<string, Record<string, number>>).U).hasOwnProperty(PR)) bad.push('PR');
    if (!(w.UI as Record<string, number>).hasOwnProperty(UI)) bad.push('UI');
    if (!(w.S as Record<string, number>).hasOwnProperty(S)) bad.push('S');
    if (!(w.CIA as Record<string, number>).hasOwnProperty(C)) bad.push('C');
    if (!(w.CIA as Record<string, number>).hasOwnProperty(I)) bad.push('I');
    if (!(w.CIA as Record<string, number>).hasOwnProperty(A)) bad.push('A');

    if (bad.length > 0) {
        return { success: false, errorType: 'UnknownMetricValue', errorMetrics: bad };
    }

    // Gather weights
    const wAV = (w.AV as Record<string, number>)[AV];
    const wAC = (w.AC as Record<string, number>)[AC];
    const wPR = ((w.PR as Record<string, Record<string, number>>)[S])[PR]; // PR depends on Scope
    const wUI = (w.UI as Record<string, number>)[UI];
    const wS = (w.S as Record<string, number>)[S];
    const wC = (w.CIA as Record<string, number>)[C];
    const wI = (w.CIA as Record<string, number>)[I];
    const wA = (w.CIA as Record<string, number>)[A];

    // Calculate Base Score
    const iss = 1 - ((1 - wC) * (1 - wI) * (1 - wA)); // Impact Sub-Score

    let impact: number;
    if (S === 'U') {
        impact = wS * iss;
    } else {
        impact = wS * (iss - 0.029) - 3.25 * Math.pow(iss - 0.02, 15);
    }

    const exploitability = EXPLOITABILITY_COEFFICIENT * wAV * wAC * wPR * wUI;

    let baseScore: number;
    if (impact <= 0) {
        baseScore = 0;
    } else if (S === 'U') {
        baseScore = roundUp1(Math.min(exploitability + impact, 10));
    } else {
        baseScore = roundUp1(Math.min(SCOPE_COEFFICIENT * (exploitability + impact), 10));
    }

    // Construct vector string
    const vectorString = `${CVSS_VERSION_ID}/AV:${AV}/AC:${AC}/PR:${PR}/UI:${UI}/S:${S}/C:${C}/I:${I}/A:${A}`;

    return {
        success: true,
        baseMetricScore: baseScore.toFixed(1),
        baseSeverity: severityRating(baseScore),
        vectorString,
        baseISS: iss,
        baseImpact: impact,
        baseExploitability: exploitability,
    };
}

// ─── Parse Vector String ────────────────────────────────────────────────────

export function parseVectorString(vectorString: string): CvssMetrics | null {
    if (!vectorString || !vectorString.startsWith(CVSS_VERSION_ID)) return null;

    const metrics: Partial<CvssMetrics> = {};
    const parts = vectorString.substring(CVSS_VERSION_ID.length + 1).split('/');

    for (const part of parts) {
        const [key, value] = part.split(':');
        if (key && value && ['AV', 'AC', 'PR', 'UI', 'S', 'C', 'I', 'A'].includes(key)) {
            (metrics as Record<string, string>)[key] = value;
        }
    }

    // Verify all metrics present
    if (metrics.AV && metrics.AC && metrics.PR && metrics.UI && metrics.S && metrics.C && metrics.I && metrics.A) {
        return metrics as CvssMetrics;
    }
    return null;
}

export function calculateCVSSFromVector(vectorString: string): CvssCalcResult {
    const metrics = parseVectorString(vectorString);
    if (!metrics) {
        return { success: false, errorType: 'MalformedVectorString' };
    }
    return calculateCVSSFromMetrics(metrics);
}

// ─── Empty Metrics ──────────────────────────────────────────────────────────

export function emptyMetrics(): CvssMetrics {
    return { AV: '', AC: '', PR: '', UI: '', S: '', C: '', I: '', A: '' };
}

export function isComplete(metrics: CvssMetrics): boolean {
    return Object.values(metrics).every(v => v !== '');
}
