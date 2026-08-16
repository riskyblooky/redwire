/**
 * Page-aware help content, keyed by pathname. Powers the "?" help button in the
 * app header (see PageHelpButton) — a short explainer of what the current page
 * is for, with an optional deep-link into the full /help guide.
 *
 * Matching is first-hit over an ordered list, so put more specific paths first.
 * Keep `body` short (a few sentences / bullets of Markdown) — it renders in a
 * modal, not a manual. The manual is /help.
 */
export interface PageHelp {
    title: string;
    body: string;
    doc?: string; // help-guide slug for the "Open the full guide" link
}

const ENTRIES: { match: (p: string) => boolean; help: PageHelp }[] = [
    {
        match: p => p === '/dashboard' || p === '/',
        help: {
            title: 'Dashboard',
            body: 'Your at-a-glance view across engagements — open work, recent activity, and quick stats. Use the engagement switcher (top-left) to scope the app to a single engagement, or jump into the **Engagements** list.',
            doc: 'user',
        },
    },
    {
        match: p => /^\/engagements\/[^/]+/.test(p),
        help: {
            title: 'Engagement workspace',
            body: 'Everything for this engagement lives in the tabs: **Findings**, **Test Cases**, **Assets**, **Attachments** (evidence), **Vault** (credentials), **Cleanup**, **Notes**, **ATT&CK**, **Activity**, and **Reporting**. Each tab loads on demand, and the count badges show totals. The **Overview** summarises status, team, and recent activity.',
            doc: 'user',
        },
    },
    {
        match: p => p === '/engagements',
        help: {
            title: 'Engagements',
            body: 'All engagements you can see. Create or propose a new one, filter to **My Engagements**, and open one to work it. Engagement lifecycle runs Proposed → Planning → Scoping → In Progress → Reporting → Completed.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/findings'),
        help: {
            title: 'Findings',
            body: 'CVSS-scored vulnerabilities. Each finding carries a severity, description, remediation, evidence, and links to the assets / test cases / vault items it relates to (shown as chips in the **Links** column). Findings have full **version history** with restore.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/testcases'),
        help: {
            title: 'Test Cases',
            body: 'The things you tried, pass/fail, organised as a tree. Link a test case to the findings it produced and the assets it touched. Import a set from a **runbook** to standardise coverage.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/assets'),
        help: {
            title: 'Assets',
            body: 'Hosts, services, URLs, and other in-scope targets. Add them by hand or bring them in from a scan via **Imports**. Smart search supports port/service dorks; linked findings and test cases show per row.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/calendar'),
        help: {
            title: 'Calendar',
            body: 'Your personal **Day / Week / Month / Gantt** view of assignments and out-of-office. Set your own OoO here — it feeds the scheduling and planning views so leads can see real availability.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/planning'),
        help: {
            title: 'Planning',
            body: 'Org-wide scheduling of all engagements. The **Timeline** tab has a **Gantt** and a **Calendar** view with a date-range filter and a *jump to engagement* picker; the **Scheduling** tab finds team availability for an engagement or window. Growth-fit highlights engagements matching an operator\'s skills.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/stats'),
        help: {
            title: 'Operations Analytics',
            body: 'Composable dashboards over your data. Build widgets with the query builder (tables, filters, aggregations), arrange them on tabbed stats pages, and share layouts.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/remediation'),
        help: {
            title: 'Remediation',
            body: 'Track findings through their fix lifecycle across the engagement. Pick an engagement to see its remediation state.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/imports'),
        help: {
            title: 'Import Scanner Output',
            body: 'Ingest Nmap / Nessus / Burp / Nuclei output into assets and findings. Start from an engagement so the import is pre-scoped, upload the file, review the **preview**, then commit. Nmap imports keep the exact command line and scan metadata as revisitable history.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/infrastructure'),
        help: {
            title: 'Infrastructure',
            body: 'Track your offensive kit — redirectors, C2, phishing infra — and link items to the findings and test cases they supported so the report shows the infrastructure behind the test.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/intelligence'),
        help: {
            title: 'Intelligence',
            body: 'OSINT and threat-intel items, plus admin-configurable RSS feeds. Link intel to the findings and test cases it informs. Feeds can be set to skip TLS verification for internal/self-signed sources.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/tags'),
        help: {
            title: 'Tags',
            body: 'Manage the tag vocabulary used to label findings and other resources for filtering and reporting.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/templates'),
        help: {
            title: 'Templates',
            body: 'Reusable building blocks — finding templates, test-case templates, runbooks, report layouts, and report themes — so you don\'t start every engagement from scratch.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/clients'),
        help: {
            title: 'Client Registry',
            body: 'Your clients and their sub-clients, with engagement history. Client info can also be edited from an engagement\'s overview.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/automations'),
        help: {
            title: 'Automations',
            body: 'Rules that react to events (e.g. a critical finding) and fire actions like notify or email. **Org Rules** apply team-wide; **My Rules** are personal and only act on events you cause.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/reports'),
        help: {
            title: 'Reporting Center',
            body: 'Generate the deliverable per engagement: **PDF** (polished), **HTML** (self-contained interactive), or **JSON** (structured, with relationships). Output honours classification / portion marking and the report theme + layout you pick.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/notifications'),
        help: {
            title: 'Notifications',
            body: 'Mentions, assignments, and automation actions. Search, filter, sort, and mark read/unread. Opt into email notifications and mute categories from your **Profile**.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/profile'),
        help: {
            title: 'Profile',
            body: 'Your name, photo, and password; enrol **TOTP** two-factor; notification (in-app + email) preferences; and your **skills**, which drive growth-fit matching on the planning page.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/search'),
        help: {
            title: 'Advanced Search',
            body: 'Boolean operators, field dorks, and quoted phrases across engagements, findings, test cases, assets, notes, and comments.',
            doc: 'user',
        },
    },
    {
        match: p => p.startsWith('/admin'),
        help: {
            title: 'Admin Console',
            body: 'Users, roles & permissions, engagement roles, configurable types, integrations (LDAP/SAML/SMTP/AI), API tokens, and the About panel. Deployment, backups, and credential rotation are covered in the **Admin Guide**.',
            doc: 'admin',
        },
    },
];

export function getPageHelp(pathname: string): PageHelp | null {
    for (const e of ENTRIES) {
        if (e.match(pathname)) return e.help;
    }
    return null;
}
