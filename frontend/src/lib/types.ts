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
    auth_provider?: string;
    must_change_password?: boolean;
    created_at: string;
    last_login?: string | null;
    last_active?: string | null;
    theme_preference?: ThemePreference;
    theme_palette?: ThemePalette;
    theme_accent_custom?: string | null;
}

export interface LoginCredentials {
    username: string;
    password: string;
}

export interface AuthTokens {
    access_token: string;
    refresh_token: string;
    token_type: string;
    requires_2fa?: boolean;
}

// Engagement types
export enum EngagementStatus {
    PLANNING = 'PLANNING',
    IN_PROGRESS = 'IN_PROGRESS',
    REPORTING = 'REPORTING',
    COMPLETED = 'COMPLETED',
    ON_HOLD = 'ON_HOLD',
}

export enum EngagementType {
    EXTERNAL_PENTEST = 'EXTERNAL_PENTEST',
    INTERNAL_PENTEST = 'INTERNAL_PENTEST',
    WEB_APPLICATION = 'WEB_APPLICATION',
    MOBILE_APPLICATION = 'MOBILE_APPLICATION',
    SOCIAL_ENGINEERING = 'SOCIAL_ENGINEERING',
    PHYSICAL_SECURITY = 'PHYSICAL_SECURITY',
    RED_TEAM = 'RED_TEAM',
    PURPLE_TEAM = 'PURPLE_TEAM',
    OTHER = 'OTHER',
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

export interface Engagement {
    id: string;
    name: string;
    client_name: string;
    client_id?: string;
    client?: Client;
    engagement_type: EngagementType;
    status: EngagementStatus;
    description?: string;
    start_date?: string;
    end_date?: string;
    created_by: string;
    updated_by?: string;
    created_at: string;
    updated_at: string;
    assigned_users?: Partial<User>[];
    assignment_details?: EngagementAssignment[];
    // Portion marking
    marking_profile_id?: string | null;
    default_classification_level?: string | null;
    default_classification_suffix?: string | null;
    ceiling_classification_level?: string | null;
}

export interface EngagementRole {
    id: string;
    name: string;
    description?: string;
}

export interface EngagementAssignment {
    user_id: string;
    engagement_id: string;
    role_id?: string;
    role?: EngagementRole;
}

// Finding types
export enum Severity {
    CRITICAL = 'CRITICAL',
    HIGH = 'HIGH',
    MEDIUM = 'MEDIUM',
    LOW = 'LOW',
    INFO = 'INFO',
}

export enum FindingStatus {
    OPEN = 'OPEN',
    IN_REVIEW = 'IN_REVIEW',
    VERIFIED = 'VERIFIED',
    CLOSED = 'CLOSED',
    FALSE_POSITIVE = 'FALSE_POSITIVE',
}

export interface Tag {
    id: string;
    name: string;
    color?: string;
}

export interface Finding {
    id: string;
    engagement_id: string;
    title: string;
    description: string;
    severity: Severity;
    status: FindingStatus;
    affected_asset?: string;
    steps_to_reproduce?: string;
    impact?: string;
    remediation?: string;
    references?: string;
    cvss_score?: number;
    cvss_vector?: string;
    created_by: string;
    updated_by?: string;
    created_by_username?: string;
    created_by_profile_photo?: string;
    created_at: string;
    updated_at: string;
    tags?: Tag[];
    assets?: Asset[];
    // Portion marking — null level = inherit
    classification_level?: string | null;
    classification_suffix?: string | null;
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
    created_by_profile_photo?: string;
    updated_by?: string;
    unresolved_thread_count?: number;
    finding_title?: string;
    testcase_title?: string;
}

// Test Case types

export interface TestCase {
    id: string;
    engagement_id?: string;
    title: string;
    category: string;
    description: string;
    steps?: string;
    expected_result?: string;
    actual_result?: string;
    is_executed: boolean;
    is_successful?: boolean;
    notes?: string;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by?: string;
    created_by_username?: string;
    created_by_profile_photo?: string;
    unresolved_thread_count?: number;
    evidence?: Evidence[];
}

// Calendar types
export interface CalendarEvent {
    id: string;
    title: string;
    description?: string;
    start_time: string;
    end_time: string;
    location?: string;
    is_all_day: boolean;
    created_by: string;
    created_at: string;
    updated_at: string;
}

// Activity Log types
export interface ActivityLog {
    id: string;
    engagement_id: string;
    user_id: string;
    action: string;
    resource_type: string;
    resource_id: string;
    resource_name?: string;
    details?: string;
    created_at: string;
    user_name?: string;
    user_profile_photo?: string;
}

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
