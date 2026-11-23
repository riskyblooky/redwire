import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export type TlsMode = 'none' | 'ldaps' | 'starttls';

export interface LdapSettings {
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

export interface LdapTraceStep {
    step: string;
    ok: boolean;
    message: string;
    elapsed_ms?: number;
}

export interface LdapTestResult {
    success: boolean;
    message: string;
    trace?: LdapTraceStep[];
}

export interface LdapLoginTestResult extends LdapTestResult {
    user?: { username: string; email: string; full_name: string } | null;
}

export interface SamlSettings {
    enabled: boolean;
    idp_entity_id: string;
    idp_sso_url: string;
    idp_slo_url: string;
    idp_x509_cert: string | null;
    sp_entity_id: string;
    want_messages_signed: boolean;
}

export interface AuthSettings {
    ldap: LdapSettings;
    saml: SamlSettings;
}

export interface LoginSplash {
    enabled: boolean;
    title: string;
    message: string;
}

const KEY = ['admin', 'auth-settings'];

/** LDAP + SAML settings and the login banner, loaded together. Not cached
 *  across visits (gcTime 0): the admin form always starts from the live
 *  configuration. */
export function useAuthSettings() {
    return useQuery({
        queryKey: KEY,
        queryFn: async () => {
            const [{ data }, { data: splash }] = await Promise.all([
                api.get<AuthSettings>('/admin/auth-settings'),
                api.get<LoginSplash>('/admin/auth-settings/splash'),
            ]);
            return { ...data, splash };
        },
        staleTime: 0,
        gcTime: 0,
        retry: 1,
    });
}

export function useSaveLdapSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (ldap: LdapSettings) =>
            (await api.put<AuthSettings>('/admin/auth-settings/ldap', ldap)).data,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

export function useSaveSamlSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (saml: SamlSettings) =>
            (await api.put<AuthSettings>('/admin/auth-settings/saml', saml)).data,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

export function useSaveLoginSplash() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (splash: LoginSplash) =>
            (await api.put<LoginSplash>('/admin/auth-settings/splash', splash)).data,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

/** Bind test against the saved LDAP settings. */
export function useTestLdapConnection() {
    return useMutation({
        mutationFn: async () =>
            (await api.post<LdapTestResult>('/admin/auth-settings/ldap/test', { username: 'test', password: 'test' })).data,
    });
}

/** Full login test (bind + search + user bind) for one directory user. */
export function useTestLdapLogin() {
    return useMutation({
        mutationFn: async (creds: { username: string; password: string }) =>
            (await api.post<LdapLoginTestResult>('/admin/auth-settings/ldap/test-login', creds)).data,
    });
}
