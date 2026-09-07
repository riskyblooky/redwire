/**
 * Which global permission(s) grant access to each admin tab. Empty array = the
 * tab is ADMIN/READ_ONLY_ADMIN-only (no delegatable permission). Keeps the admin
 * page and AdminGuard in agreement so a delegated permission-holder can enter
 * the admin area and see only the tabs they can actually manage.
 *
 * Permission strings are the enum values from backend models/permission.py.
 */
export const ADMIN_TAB_PERMISSIONS: Record<string, string[]> = {
    users: ['view_all_users', 'manage_users'],
    permissions: ['manage_groups', 'manage_engagement_roles'],
    'registration-codes': ['manage_registration_codes'],
    types: ['manage_configurable_types'],
    authentication: [],            // LDAP/SAML/SMTP config — admin-only
    'api-tokens': [],              // admin-only
    wordlists: [],                 // admin-only (upload/delete are role-gated)
    ai: [],                        // admin-only
    skills: ['skill_create', 'skill_edit', 'skill_delete', 'skill_manage_categories'],
    widgets: ['manage_dashboard_widgets'],
    'custom-fields': ['manage_custom_fields'],
    plugins: [],                   // admin-only
    email: [],                     // admin-only
};

/** Tab render order — matches the TabsList in the admin page. */
export const ADMIN_TAB_ORDER = [
    'users', 'permissions', 'registration-codes', 'types', 'authentication',
    'api-tokens', 'wordlists', 'ai', 'skills', 'widgets', 'custom-fields',
    'plugins', 'email',
];

/** The union of delegatable admin-surface permissions — holding ANY of these
 *  grants entry to the admin area (in addition to the admin roles). */
export const ADMIN_SURFACE_PERMISSIONS: string[] = Array.from(
    new Set(Object.values(ADMIN_TAB_PERMISSIONS).flat())
);

/** Can this user see a given admin tab? Admin roles see everything; otherwise
 *  the user must hold one of the tab's permissions. */
export function canSeeAdminTab(tab: string, isAdminView: boolean, perms: string[]): boolean {
    if (isAdminView) return true;
    const required = ADMIN_TAB_PERMISSIONS[tab] || [];
    return required.length > 0 && required.some((p) => perms.includes(p));
}
