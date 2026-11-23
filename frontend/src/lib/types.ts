/**
 * Context passed to the in-editor AI assistant (the "Ask AI" panel in the
 * markdown editor). `resourceType`/`fieldName` label what is being edited;
 * `entityContext` is an optional bag of read-only facts about the record
 * (title, severity, CVSS, status, …) that the backend renders into the AI
 * system prompt so suggestions are grounded in the actual record. Values are
 * plain scalars; empties are dropped before sending.
 */
export interface EditorFieldContext {
    resourceType: string;
    fieldName: string;
    entityContext?: Record<string, string | number | null | undefined>;
}

// User types
export enum UserRole {
    ADMIN = 'admin',
    READ_ONLY_ADMIN = 'read_only_admin',
    TEAM_LEAD = 'team_lead',
    OPERATOR = 'operator',
    READ_ONLY = 'read_only',
}

export type ThemePreference = 'purple' | 'crimson' | 'blue' | 'emerald' | 'amber' | 'custom';
export type ThemePalette = 'aurora' | 'operator' | 'half-dark' | 'light';

export interface User {
    id: string;
    username: string;
    email: string;
    full_name?: string | null;
    profile_photo?: string | null;
    role: UserRole;
    is_active: boolean;
    totp_enabled?: boolean;
    // Count of un-consumed 2FA recovery codes. Settings UI warns when
    // this gets low. GHSA-vm6w-9wm5-q367 follow-up.
    recovery_codes_remaining?: number;
    auth_provider?: string;
    must_change_password?: boolean;
    created_at: string;
    last_login?: string | null;
    last_active?: string | null;
    theme_preference?: ThemePreference;
    theme_palette?: ThemePalette;
    theme_accent_custom?: string | null;
}

// Engagement types
export enum EngagementStatus {
    PLANNING = 'PLANNING',
    IN_PROGRESS = 'IN_PROGRESS',
    REPORTING = 'REPORTING',
    COMPLETED = 'COMPLETED',
    ON_HOLD = 'ON_HOLD',
}

// Client types
export interface ClientType {
    id: string;
    name: string;
    description?: string;
    color: string;
    is_system: boolean;
    sort_order: number;
}

export interface Client {
    custom_fields?: Record<string, unknown>;
    id: string;
    name: string;
    description?: string;
    client_type_id?: string;
    client_type?: ClientType;
    parent_id?: string;
    sort_order: number;
    contact_name?: string;
    contact_email?: string;
    notes?: string;
    created_at: string;
    updated_at: string;
    created_by?: string;
    engagement_count: number;
    children?: Client[];
}

// Finding types
export enum Severity {
    CRITICAL = 'CRITICAL',
    HIGH = 'HIGH',
    MEDIUM = 'MEDIUM',
    LOW = 'LOW',
    INFO = 'INFO',
}

// Asset types

export interface AssetPort {
    id: string;
    asset_id: string;
    port_number: number;
    protocol: 'TCP' | 'UDP';
    service_name?: string;
    state: 'OPEN' | 'CLOSED' | 'FILTERED';
    version?: string;
}

export interface Asset {
    custom_fields?: Record<string, unknown>;
    id: string;
    engagement_id: string;
    name: string;
    asset_type: string;
    identifier: string;
    description?: string;
    notes?: string;
    is_pwned: boolean;
    is_scanned: boolean;
    in_scope: boolean;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by?: string;
    created_by_username?: string;
    created_by_full_name?: string;
    created_by_profile_photo?: string;
    unresolved_thread_count?: number;
    cleanup_artifacts?: any[];
    vault_items?: any[];
    testcases?: { id: string; title: string; category: string }[];
    ports?: AssetPort[];
}

// Evidence types
export interface Evidence {
    id: string;
    finding_id?: string;
    testcase_id?: string;
    engagement_id?: string;
    filename: string;
    original_filename: string;
    file_size: number;
    mime_type?: string;
    description?: string;
    include_in_report: boolean;
    classification_level?: string | null;
    classification_suffix?: string | null;
    created_at: string;
    updated_at: string;
    created_by: string;
    created_by_username?: string;
    created_by_full_name?: string;
    created_by_profile_photo?: string;
    updated_by?: string;
    unresolved_thread_count?: number;
    finding_title?: string;
    testcase_title?: string;
    finding_status?: string;
}

// Test Case types

// Activity Log types

// Registration Code types
export interface RegistrationCode {
    id: string;
    code: string;
    label?: string;
    max_uses: number;
    used_count: number;
    expires_at?: string;
    created_at: string;
    created_by: string;
    is_active: boolean;
}

// Report Layout types
export const SectionType = {
    TEXT: 'text',
    FINDINGS: 'findings',
    TESTCASES: 'testcases',
    CLEANUP_ARTIFACTS: 'cleanup_artifacts',
} as const;

export type SectionType = typeof SectionType[keyof typeof SectionType];

export interface ReportSection {
    id: string;
    section_type: SectionType;
    title: string;
    content: string;
    sort_order: number;
    classification_level?: string | null;
    classification_suffix?: string | null;
    page_break_before?: boolean | null;
}

export interface ReportLayout {
    id: string;
    name: string;
    engagement_id: string;
    is_default: boolean;
    sections: ReportSection[];
    created_at: string;
    updated_at: string;
    created_by?: string;
    updated_by?: string;
}

export interface ReportLayoutTemplateSection {
    id: string;
    section_type: SectionType;
    title: string;
    content: string;
    sort_order: number;
}

export interface ReportLayoutTemplate {
    id: string;
    name: string;
    description?: string;
    sections: ReportLayoutTemplateSection[];
    created_at: string;
    updated_at: string;
    created_by?: string;
    updated_by?: string;
}
