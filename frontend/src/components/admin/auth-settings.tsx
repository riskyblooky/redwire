'use client';

import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';

type TlsMode = 'none' | 'ldaps' | 'starttls';

interface LdapSettings {
    enabled: boolean;
    server_url: string;
    bind_dn: string;
    bind_password: string | null;
    search_base: string;
    search_filter: string;
    username_attribute: string;
    email_attribute: string;
    fullname_attribute: string;
    tls_mode: TlsMode;
    tls_verify: boolean;
    debug_enabled: boolean;
}

interface LdapTraceStep {
    step: string;
    ok: boolean;
    message: string;
    elapsed_ms?: number;
}

interface LdapTestResult {
    success: boolean;
    message: string;
    trace?: LdapTraceStep[];
}

interface SamlSettings {
    enabled: boolean;
    idp_entity_id: string;
    idp_sso_url: string;
    idp_slo_url: string;
    idp_x509_cert: string | null;
    sp_entity_id: string;
    want_messages_signed: boolean;
}

interface AuthSettings {
    ldap: LdapSettings;
    saml: SamlSettings;
}

const DEFAULT_LDAP: LdapSettings = {
    enabled: false,
    server_url: '',
    bind_dn: '',
    bind_password: null,
    search_base: '',
    search_filter: '(uid={username})',
    username_attribute: 'uid',
    email_attribute: 'mail',
    fullname_attribute: 'cn',
    tls_mode: 'ldaps',
    tls_verify: true,
    debug_enabled: false,
};

const DEFAULT_SAML: SamlSettings = {
    enabled: false,
    idp_entity_id: '',
    idp_sso_url: '',
    idp_slo_url: '',
    idp_x509_cert: null,
    sp_entity_id: '',
    want_messages_signed: false,
};

export function AuthSettingsManagement() {
    const [ldap, setLdap] = useState<LdapSettings>(DEFAULT_LDAP);
    const [saml, setSaml] = useState<SamlSettings>(DEFAULT_SAML);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testResult, setTestResult] = useState<LdapTestResult | null>(null);
    const [testingLdap, setTestingLdap] = useState(false);
    const [successMessage, setSuccessMessage] = useState('');
    const [splash, setSplash] = useState({ enabled: false, title: '', message: '' });
    const [savingSplash, setSavingSplash] = useState(false);

    const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const getToken = () => localStorage.getItem('access_token') || '';

    const fetchSettings = useCallback(async () => {
        try {
            const [authRes, splashRes] = await Promise.all([
                fetch(`${API}/admin/auth-settings`, {
                    headers: { Authorization: `Bearer ${getToken()}` },
                }),
                fetch(`${API}/admin/auth-settings/splash`, {
                    headers: { Authorization: `Bearer ${getToken()}` },
                }),
            ]);
            if (authRes.ok) {
                const data: AuthSettings = await authRes.json();
                setLdap(data.ldap);
                setSaml(data.saml);
            }
            if (splashRes.ok) {
                const data = await splashRes.json();
                setSplash(data);
            }
        } catch (e) {
            console.error('Failed to load settings', e);
        } finally {
            setLoading(false);
        }
    }, [API]);

    useEffect(() => {
        fetchSettings();
    }, [fetchSettings]);

    // Surface a non-2xx response as a toast. Tries to pull FastAPI's
    // {detail: "..."} message; falls back to status text or HTTP code.
    const reportFetchError = async (res: Response, fallback: string) => {
        let detail = `${fallback} (HTTP ${res.status})`;
        try {
            const body = await res.json();
            if (body?.detail) detail = String(body.detail);
        } catch { /* response wasn't JSON */ }
        toast.error(detail);
    };

    const saveLdap = async () => {
        setSaving(true);
        setSuccessMessage('');
        try {
            const res = await fetch(`${API}/admin/auth-settings/ldap`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify(ldap),
            });
            if (res.ok) {
                const data: AuthSettings = await res.json();
                setLdap(data.ldap);
                setSuccessMessage('LDAP settings saved successfully');
                setTimeout(() => setSuccessMessage(''), 3000);
            } else {
                await reportFetchError(res, 'Failed to save LDAP settings');
            }
        } catch (e) {
            toast.error(`Failed to save LDAP settings: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            setSaving(false);
        }
    };

    const saveSaml = async () => {
        setSaving(true);
        setSuccessMessage('');
        try {
            const res = await fetch(`${API}/admin/auth-settings/saml`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify(saml),
            });
            if (res.ok) {
                const data: AuthSettings = await res.json();
                setSaml(data.saml);
                setSuccessMessage('SAML settings saved successfully');
                setTimeout(() => setSuccessMessage(''), 3000);
            } else {
                await reportFetchError(res, 'Failed to save SAML settings');
            }
        } catch (e) {
            toast.error(`Failed to save SAML settings: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            setSaving(false);
        }
    };

    const testLdapConnection = async () => {
        setTestingLdap(true);
        setTestResult(null);
        try {
            const res = await fetch(`${API}/admin/auth-settings/ldap/test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify({ username: 'test', password: 'test' }),
            });
            const data = await res.json();
            setTestResult(data);
        } catch (e) {
            setTestResult({ success: false, message: String(e) });
        } finally {
            setTestingLdap(false);
        }
    };

    const saveSplash = async () => {
        setSavingSplash(true);
        setSuccessMessage('');
        try {
            const res = await fetch(`${API}/admin/auth-settings/splash`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${getToken()}`,
                },
                body: JSON.stringify(splash),
            });
            if (res.ok) {
                const data = await res.json();
                setSplash(data);
                setSuccessMessage('Login banner settings saved successfully');
                setTimeout(() => setSuccessMessage(''), 3000);
            } else {
                await reportFetchError(res, 'Failed to save login banner');
            }
        } catch (e) {
            toast.error(`Failed to save login banner: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
            setSavingSplash(false);
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Success banner */}
            {successMessage && (
                <div className="bg-green-500/10 border border-green-500/30 text-green-400 px-4 py-3 rounded-lg text-sm">
                    {successMessage}
                </div>
            )}

            {/* ── LDAP Section ────────────────────────────────────── */}
            <div className="bg-card rounded-xl border border-border overflow-hidden">
                <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-white">LDAP / Active Directory</h3>
                        <p className="text-sm text-muted-foreground mt-1">
                            Authenticate users against an LDAP or Active Directory server
                        </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            checked={ldap.enabled}
                            onChange={(e) => setLdap({ ...ldap, enabled: e.target.checked })}
                            className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
                    </label>
                </div>
                <div className="p-6 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Server URL</label>
                            <input
                                type="text"
                                value={ldap.server_url}
                                onChange={(e) => setLdap({ ...ldap, server_url: e.target.value })}
                                placeholder="ldap://ldap.example.com:389"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Search Base</label>
                            <input
                                type="text"
                                value={ldap.search_base}
                                onChange={(e) => setLdap({ ...ldap, search_base: e.target.value })}
                                placeholder="dc=example,dc=com"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Bind DN</label>
                            <input
                                type="text"
                                value={ldap.bind_dn}
                                onChange={(e) => setLdap({ ...ldap, bind_dn: e.target.value })}
                                placeholder="cn=admin,dc=example,dc=com"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Bind Password</label>
                            <input
                                type="password"
                                value={ldap.bind_password ?? ''}
                                onChange={(e) => setLdap({ ...ldap, bind_password: e.target.value })}
                                placeholder="••••••••"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Search Filter</label>
                            <input
                                type="text"
                                value={ldap.search_filter}
                                onChange={(e) => setLdap({ ...ldap, search_filter: e.target.value })}
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Username Attribute</label>
                            <input
                                type="text"
                                value={ldap.username_attribute}
                                onChange={(e) => setLdap({ ...ldap, username_attribute: e.target.value })}
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">Email Attribute</label>
                            <input
                                type="text"
                                value={ldap.email_attribute}
                                onChange={(e) => setLdap({ ...ldap, email_attribute: e.target.value })}
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                    </div>

                    <div className="pt-2 space-y-3">
                        <div>
                            <label className="block text-sm text-foreground/80 mb-1.5">TLS mode</label>
                            <select
                                value={ldap.tls_mode}
                                onChange={(e) => setLdap({ ...ldap, tls_mode: e.target.value as TlsMode })}
                                className="w-full max-w-xs bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            >
                                <option value="ldaps">LDAPS (TLS from connect) — use with ldaps:// URL</option>
                                <option value="starttls">StartTLS — plain ldap:// then upgrade</option>
                                <option value="none">None — plain LDAP, no encryption (not recommended)</option>
                            </select>
                            {ldap.tls_mode === 'none' && (
                                <p className="mt-1.5 text-xs text-amber-400">
                                    Credentials will cross the network in cleartext. Use only on trusted internal networks.
                                </p>
                            )}
                        </div>

                        {ldap.tls_mode !== 'none' && (
                            <label className="flex items-start gap-2 text-sm text-foreground/80 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={ldap.tls_verify}
                                    onChange={(e) => setLdap({ ...ldap, tls_verify: e.target.checked })}
                                    className="mt-0.5 rounded bg-secondary border-border text-primary focus:ring-primary"
                                />
                                <span>
                                    Verify server certificate
                                    {!ldap.tls_verify && (
                                        <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                            insecure
                                        </span>
                                    )}
                                    <span className="block text-xs text-foreground/60 mt-0.5">
                                        Uncheck for self-signed / internal CA servers when you can't ship a CA cert.
                                        Vulnerable to MITM on the LDAP connection when disabled.
                                    </span>
                                </span>
                            </label>
                        )}

                        <label className="flex items-start gap-2 text-sm text-foreground/80 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={ldap.debug_enabled}
                                onChange={(e) => setLdap({ ...ldap, debug_enabled: e.target.checked })}
                                className="mt-0.5 rounded bg-secondary border-border text-primary focus:ring-primary"
                            />
                            <span>
                                Enable connection debugging
                                {ldap.debug_enabled && (
                                    <span className="ml-2 inline-block px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-blue-500/15 text-blue-400 border border-blue-500/30">
                                        debug on
                                    </span>
                                )}
                                <span className="block text-xs text-foreground/60 mt-0.5">
                                    Emits a per-step <code className="text-[11px]">[LDAP DEBUG]</code> trace
                                    (server URL, TLS mode, bind DN, actual filter, entry counts, timings)
                                    on real logins to the backend log, and returns the same trace in the
                                    Test Connection response. Passwords are never included. Turn off when
                                    you're done — the logs get noisy.
                                </span>
                            </span>
                        </label>
                    </div>

                    <div className="flex items-center gap-3 pt-4 border-t border-border/50">
                        <button
                            onClick={saveLdap}
                            disabled={saving}
                            className="px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            {saving ? 'Saving...' : 'Save LDAP Settings'}
                        </button>
                        <button
                            onClick={testLdapConnection}
                            disabled={testingLdap}
                            className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            {testingLdap ? 'Testing...' : 'Test Connection'}
                        </button>
                        {testResult && (
                            <span className={`text-sm ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                                {testResult.message}
                            </span>
                        )}
                    </div>

                    {testResult?.trace && testResult.trace.length > 0 && (
                        <div className="mt-4 rounded-lg border border-border/60 bg-secondary/20">
                            <div className="px-3 py-2 border-b border-border/60 flex items-center justify-between">
                                <span className="text-xs font-semibold text-foreground/80 uppercase tracking-wider">
                                    Connection trace
                                </span>
                                <span className="text-[10px] text-foreground/50">
                                    {testResult.trace.length} step{testResult.trace.length === 1 ? '' : 's'}
                                </span>
                            </div>
                            <ol className="divide-y divide-border/40 font-mono text-[11px]">
                                {testResult.trace.map((step, i) => (
                                    <li key={i} className="px-3 py-1.5 flex items-start gap-2">
                                        <span className={step.ok ? 'text-green-400 shrink-0' : 'text-red-400 shrink-0'}>
                                            {step.ok ? '✓' : '✗'}
                                        </span>
                                        <span className="text-primary shrink-0 min-w-[8rem]">
                                            {step.step}
                                        </span>
                                        <span className="text-foreground/70 flex-1 break-all">
                                            {step.message}
                                        </span>
                                        {step.elapsed_ms !== undefined && (
                                            <span className="text-foreground/40 shrink-0">
                                                {step.elapsed_ms.toFixed(1)}ms
                                            </span>
                                        )}
                                    </li>
                                ))}
                            </ol>
                        </div>
                    )}
                </div>
            </div>

            {/* ── SAML SSO Section ────────────────────────────────── */}
            <div className="bg-card rounded-xl border border-border overflow-hidden">
                <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-white">SAML 2.0 SSO</h3>
                        <p className="text-sm text-muted-foreground mt-1">
                            Single Sign-On via a SAML 2.0 Identity Provider (Okta, Azure AD, etc.)
                        </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            checked={saml.enabled}
                            onChange={(e) => setSaml({ ...saml, enabled: e.target.checked })}
                            className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-primary peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
                    </label>
                </div>
                <div className="p-6 space-y-4">
                    {/* SP info banner */}
                    <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
                        <p className="text-sm text-primary font-medium mb-2">Service Provider Info</p>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                            <div>
                                <span className="text-muted-foreground">ACS URL:</span>{' '}
                                <code className="text-primary">{`${API}/auth/saml/acs`}</code>
                            </div>
                            <div>
                                <span className="text-muted-foreground">Metadata URL:</span>{' '}
                                <code className="text-primary">{`${API}/auth/saml/metadata`}</code>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">IdP Entity ID</label>
                            <input
                                type="text"
                                value={saml.idp_entity_id}
                                onChange={(e) => setSaml({ ...saml, idp_entity_id: e.target.value })}
                                placeholder="https://idp.example.com/metadata"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">SP Entity ID</label>
                            <input
                                type="text"
                                value={saml.sp_entity_id}
                                onChange={(e) => setSaml({ ...saml, sp_entity_id: e.target.value })}
                                placeholder={`${API}/auth/saml/metadata`}
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">IdP SSO URL</label>
                            <input
                                type="text"
                                value={saml.idp_sso_url}
                                onChange={(e) => setSaml({ ...saml, idp_sso_url: e.target.value })}
                                placeholder="https://idp.example.com/sso"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-muted-foreground mb-1">IdP SLO URL (optional)</label>
                            <input
                                type="text"
                                value={saml.idp_slo_url}
                                onChange={(e) => setSaml({ ...saml, idp_slo_url: e.target.value })}
                                placeholder="https://idp.example.com/slo"
                                className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-primary focus:outline-hidden"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm text-muted-foreground mb-1">IdP X.509 Certificate</label>
                        <textarea
                            value={saml.idp_x509_cert ?? ''}
                            onChange={(e) => setSaml({ ...saml, idp_x509_cert: e.target.value })}
                            placeholder="Paste the IdP's public certificate here (PEM format, without header/footer)"
                            rows={4}
                            className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm font-mono focus:border-primary focus:outline-hidden resize-none"
                        />
                    </div>

                    <div className="flex items-start gap-3 pt-2">
                        <input
                            type="checkbox"
                            id="saml-want-messages-signed"
                            checked={saml.want_messages_signed}
                            onChange={(e) => setSaml({ ...saml, want_messages_signed: e.target.checked })}
                            className="mt-1 accent-primary"
                        />
                        <label htmlFor="saml-want-messages-signed" className="text-sm text-muted-foreground">
                            Require signed SAML <code className="text-xs bg-muted px-1 rounded">&lt;Response&gt;</code> envelope
                            <span className="block text-xs text-muted-foreground/70 mt-0.5">
                                Off by default — most IdPs sign only the inner Assertion. Enable only after confirming your IdP signs the
                                outer Response message; otherwise SSO logins will fail.
                            </span>
                        </label>
                    </div>

                    <div className="flex items-center gap-3 pt-4 border-t border-border/50">
                        <button
                            onClick={saveSaml}
                            disabled={saving}
                            className="px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            {saving ? 'Saving...' : 'Save SAML Settings'}
                        </button>
                        <a
                            href={`${API}/auth/saml/metadata`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-white rounded-lg text-sm font-medium transition-colors inline-block"
                        >
                            Download SP Metadata
                        </a>
                    </div>
                </div>
            </div>

            {/* ── Login Banner / Splash Screen ─────────────────────── */}
            <div className="bg-card rounded-xl border border-border overflow-hidden">
                <div className="px-6 py-4 border-b border-border flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-white">Login Banner</h3>
                        <p className="text-sm text-muted-foreground mt-1">
                            Configurable splash screen shown before the login form (e.g. DoD consent banner)
                        </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input
                            type="checkbox"
                            checked={splash.enabled}
                            onChange={(e) => setSplash({ ...splash, enabled: e.target.checked })}
                            className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-muted rounded-full peer peer-checked:bg-amber-500 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
                    </label>
                </div>
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm text-muted-foreground mb-1">Banner Title</label>
                        <input
                            type="text"
                            value={splash.title}
                            onChange={(e) => setSplash({ ...splash, title: e.target.value })}
                            placeholder="NOTICE TO USERS"
                            className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-amber-500 focus:outline-hidden"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-muted-foreground mb-1">Banner Message</label>
                        <textarea
                            value={splash.message}
                            onChange={(e) => setSplash({ ...splash, message: e.target.value })}
                            placeholder="You are accessing a U.S. Government information system...."
                            rows={6}
                            className="w-full bg-background text-white border border-border rounded-lg px-3 py-2 text-sm focus:border-amber-500 focus:outline-hidden resize-none"
                        />
                    </div>

                    {/* Live Preview */}
                    {splash.enabled && (splash.title || splash.message) && (
                        <div>
                            <label className="block text-sm text-muted-foreground mb-2">Preview</label>
                            <div className="rounded-xl border-2 border-amber-500/60 bg-[#0c0c10]/95 shadow-[0_0_20px_rgba(245,158,11,0.1)] overflow-hidden">
                                <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-2 flex items-center gap-2">
                                    <span className="text-[11px] font-mono font-bold text-amber-400 uppercase tracking-widest">
                                        ⚠ {splash.title || 'NOTICE'} ⚠
                                    </span>
                                </div>
                                <div className="px-4 py-4">
                                    <div className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap font-mono">
                                        {splash.message || '(no message)'}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    <div className="flex items-center gap-3 pt-4 border-t border-border/50">
                        <button
                            onClick={saveSplash}
                            disabled={savingSplash}
                            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            {savingSplash ? 'Saving...' : 'Save Banner Settings'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Info box */}
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 text-sm text-amber-300">
                <p className="font-medium mb-1">How It Works</p>
                <ul className="list-disc list-inside space-y-1 text-xs text-amber-300/80">
                    <li>LDAP: Users authenticate with their directory credentials. New users are auto-provisioned on first login.</li>
                    <li>SAML SSO: Users click &quot;Sign in with SSO&quot; on the login page and are redirected to your IdP.</li>
                    <li>Local login always remains available. LDAP and SAML are additional options.</li>
                    <li>Auto-provisioned users are assigned the Operator role and default group.</li>
                </ul>
            </div>
        </div>
    );
}
