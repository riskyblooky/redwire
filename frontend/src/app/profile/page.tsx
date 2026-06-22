/**
 * profile/page.tsx — User Profile & Settings Page
 *
 * Four-tab settings hub for the authenticated user:
 *
 * **Profile tab**
 *  - Avatar with click-to-upload (camera overlay).
 *  - General information form (full name, email).
 *  - Password change form with real-time wordlist breach check.
 *
 * **Skills tab** (`SkillsTab` sub-component)
 *  - Radar chart comparing the user's proficiency to the team average.
 *  - Category-grouped skill selectors with 5-level (Novice → Expert)
 *    proficiency buttons. Save persists via `useSetMySkills`.
 *
 * **Security tab**
 *  - TOTP-based 2FA setup/disable flow (QR code, manual secret, verify).
 *  - API Tokens card (`<ApiTokensCard>`).
 *
 * **Notifications tab**
 *  - Delegated to `<NotificationSettingsCard>`.
 *
 * Hooks: `useUpdateProfile`, `useUpdatePassword`, `useUploadProfilePhoto`,
 * `useCheckPassword` (wordlist breach check), `useSkillCategories`,
 * `useUserSkills`, `useSetMySkills`, `useAverageSkills`,
 * `useNotificationPreferences`, `useUpdateNotificationPreferences`.
 */
'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useAuthStore } from '@/stores/auth-store';
import { type ThemePreference, type ThemePalette } from '@/lib/types';
import {
    useUpdateProfile,
    useUpdatePassword,
    useUploadProfilePhoto
} from '@/lib/hooks/use-profile';
import { Loader2, Camera, Mail, User, Lock, CheckCircle2, AlertCircle, Shield, ShieldCheck, ShieldOff, Copy, Eye, EyeOff, AlertTriangle, BellRing, Radar, Save, Target, Palette, Check, RefreshCw, Download } from 'lucide-react';
import { useCheckPassword } from '@/lib/hooks/use-wordlist';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';
import { ApiTokensCard } from '@/components/profile/api-tokens-card';
import { useNotificationPreferences, useUpdateNotificationPreferences } from '@/lib/hooks/use-notifications';
import { Switch } from '@/components/ui/switch';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useSkillCategories, useUserSkills, useSetMySkills, useAverageSkills, SKILL_LEVELS, MAX_GROWTH_FOCUSES } from '@/lib/hooks/use-skills';
import { SkillsRadarChart, buildCategoryRadarData } from '@/components/ui/skills-radar-chart';

const TABS = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'skills', label: 'Skills', icon: Radar },
    { id: 'security', label: 'Security', icon: Shield },
    { id: 'notifications', label: 'Notifications', icon: BellRing },
] as const;

type TabId = typeof TABS[number]['id'];

export default function ProfilePage() {
    const { user } = useAuthStore();
    const [activeTab, setActiveTab] = useState<TabId>('profile');
    const updateProfile = useUpdateProfile();
    const updatePassword = useUpdatePassword();
    const uploadPhoto = useUploadProfilePhoto();
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Profile info state
    const [profileData, setProfileData] = useState({
        full_name: '',
        email: '',
    });
    // Step-up state for the email-change gate (GHSA-hc9w-hggj-r52w).
    const [emailChangePassword, setEmailChangePassword] = useState('');
    const [emailChangeTotpCode, setEmailChangeTotpCode] = useState('');

    // Populate form when user data loads
    useEffect(() => {
        if (user) {
            setProfileData({
                full_name: user.full_name || '',
                email: user.email || '',
            });
        }
    }, [user]);

    const emailChanged = !!user && profileData.email !== (user.email || '');
    const isLocalUser = !user?.auth_provider || user.auth_provider === 'local';

    // Password change state
    const [passwordData, setPasswordData] = useState({
        old_password: '',
        new_password: '',
        confirm_password: '',
        totp_code: '',
    });

    const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
    const [passwordMessage, setPasswordMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

    // 2FA state
    const [totpSetup, setTotpSetup] = useState<{ secret: string; qr_code: string; otpauth_uri: string } | null>(null);
    const [totpCode, setTotpCode] = useState('');
    const [totpLoading, setTotpLoading] = useState(false);
    const [showDisable, setShowDisable] = useState(false);
    const [disablePassword, setDisablePassword] = useState('');
    const [disableCode, setDisableCode] = useState('');
    const [showSecret, setShowSecret] = useState(false);
    // Setup requires the current password (mirrors disable) — see GHSA-vm6w-9wm5-q367
    const [showSetupPrompt, setShowSetupPrompt] = useState(false);
    const [setupPassword, setSetupPassword] = useState('');

    // GHSA-vm6w-9wm5-q367 follow-up: recovery codes shown once after
    // /totp/verify-setup or /totp/recovery-codes/regenerate. Held in a
    // modal until the user explicitly confirms they've saved them.
    // Never re-fetchable — backend stores hashes only.
    const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
    const [recoveryAcknowledged, setRecoveryAcknowledged] = useState(false);

    // Regenerate flow — same shape as disable (requires password + TOTP).
    const [showRegenerate, setShowRegenerate] = useState(false);
    const [regeneratePassword, setRegeneratePassword] = useState('');
    const [regenerateCode, setRegenerateCode] = useState('');
    const [regenerateLoading, setRegenerateLoading] = useState(false);

    // Wordlist check for new password
    const checkPassword = useCheckPassword();
    const [wordlistWarning, setWordlistWarning] = useState(false);
    const [wordlistChecking, setWordlistChecking] = useState(false);

    useEffect(() => {
        const pw = passwordData.new_password;
        if (!pw || pw.length < 3) {
            setWordlistWarning(false);
            return;
        }
        setWordlistChecking(true);
        const timer = setTimeout(async () => {
            try {
                const res = await checkPassword.mutateAsync(pw);
                setWordlistWarning(res.found);
            } catch {
                setWordlistWarning(false);
            } finally {
                setWordlistChecking(false);
            }
        }, 500);
        return () => { clearTimeout(timer); setWordlistChecking(false); };
    }, [passwordData.new_password]);

    const handleProfileSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setProfileMessage(null);
        try {
            // Email change requires a credential-class step-up (GHSA-hc9w-hggj-r52w).
            // Only send the step-up fields when the email actually changed,
            // so unrelated profile edits don't ping the user for a password.
            const payload: typeof profileData & { current_password?: string; totp_code?: string } = { ...profileData };
            if (emailChanged && isLocalUser) {
                payload.current_password = emailChangePassword;
                if (user?.totp_enabled) payload.totp_code = emailChangeTotpCode;
            }
            await updateProfile.mutateAsync(payload);
            setProfileMessage({ type: 'success', text: 'Profile updated successfully!' });
            setEmailChangePassword('');
            setEmailChangeTotpCode('');
            // Email change revokes all sessions server-side — bounce to login.
            if (emailChanged) {
                setProfileMessage({ type: 'success', text: 'Email updated. Signing you out…' });
                setTimeout(() => {
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
                    window.location.href = '/login';
                }, 1200);
            }
        } catch (error: any) {
            setProfileMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to update profile' });
            setEmailChangePassword('');
            setEmailChangeTotpCode('');
        }
    };

    const handlePasswordSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setPasswordMessage(null);

        if (passwordData.new_password !== passwordData.confirm_password) {
            setPasswordMessage({ type: 'error', text: 'New passwords do not match' });
            return;
        }

        if (user?.totp_enabled && passwordData.totp_code.length !== 6) {
            setPasswordMessage({ type: 'error', text: 'Enter your 6-digit 2FA code' });
            return;
        }

        try {
            await updatePassword.mutateAsync({
                old_password: passwordData.old_password,
                new_password: passwordData.new_password,
                ...(user?.totp_enabled ? { totp_code: passwordData.totp_code } : {}),
            });
            setPasswordMessage({ type: 'success', text: 'Password changed. Signing you out…' });
            setPasswordData({ old_password: '', new_password: '', confirm_password: '', totp_code: '' });
            // All sessions were revoked server-side; force a fresh login.
            setTimeout(() => {
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
                window.location.href = '/login';
            }, 1200);
            return;
        } catch (error: any) {
            setPasswordMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to change password' });
        }
    };

    const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            await uploadPhoto.mutateAsync(file);
            setProfileMessage({ type: 'success', text: 'Profile photo updated!' });
        } catch (error: any) {
            setProfileMessage({ type: 'error', text: 'Failed to upload photo' });
        }
    };

    // 2FA handlers
    const handleTotpSetup = async () => {
        setTotpLoading(true);
        try {
            const res = await api.post('/auth/totp/setup', { password: setupPassword });
            setTotpSetup(res.data);
            setShowSetupPrompt(false);
            setSetupPassword('');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to start 2FA setup');
        } finally {
            setTotpLoading(false);
        }
    };

    const handleTotpVerify = async () => {
        setTotpLoading(true);
        try {
            const res = await api.post('/auth/totp/verify-setup', { code: totpCode });
            toast.success('Two-factor authentication enabled!');
            setTotpSetup(null);
            setTotpCode('');
            // Surface the freshly-issued recovery codes — modal blocks
            // until the user confirms they've saved them.
            if (Array.isArray(res.data?.recovery_codes)) {
                setRecoveryCodes(res.data.recovery_codes);
                setRecoveryAcknowledged(false);
            }
            // Refresh user data
            const userRes = await api.get('/auth/me');
            setUser(userRes.data);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Invalid code. Please try again.');
            setTotpCode('');
        } finally {
            setTotpLoading(false);
        }
    };

    const handleRegenerateCodes = async () => {
        setRegenerateLoading(true);
        try {
            const res = await api.post('/auth/totp/recovery-codes/regenerate', {
                password: regeneratePassword,
                code: regenerateCode,
            });
            toast.success('Recovery codes regenerated. Save the new ones — the old set is no longer valid.');
            setShowRegenerate(false);
            setRegeneratePassword('');
            setRegenerateCode('');
            if (Array.isArray(res.data?.recovery_codes)) {
                setRecoveryCodes(res.data.recovery_codes);
                setRecoveryAcknowledged(false);
            }
            const userRes = await api.get('/auth/me');
            setUser(userRes.data);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to regenerate recovery codes');
        } finally {
            setRegenerateLoading(false);
        }
    };

    const handleCopyAllCodes = () => {
        if (!recoveryCodes) return;
        navigator.clipboard.writeText(recoveryCodes.join('\n'));
        toast.success('All 10 recovery codes copied to clipboard');
    };

    const handleDownloadCodes = () => {
        if (!recoveryCodes) return;
        const header = [
            `# RedWire 2FA recovery codes for ${user?.username || 'user'}`,
            `# Generated: ${new Date().toISOString()}`,
            `# Each code is single-use. Treat this file like a password — store it`,
            `# somewhere safe (password manager, printed copy in a sealed envelope).`,
            ``,
        ].join('\n');
        const body = recoveryCodes.join('\n') + '\n';
        const blob = new Blob([header + body], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `redwire-recovery-codes-${user?.username || 'user'}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const handleTotpDisable = async () => {
        setTotpLoading(true);
        try {
            await api.post('/auth/totp/disable', { password: disablePassword, code: disableCode });
            toast.success('Two-factor authentication disabled.');
            setShowDisable(false);
            setDisablePassword('');
            setDisableCode('');
            const userRes = await api.get('/auth/me');
            setUser(userRes.data);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to disable 2FA');
        } finally {
            setTotpLoading(false);
        }
    };

    const { setUser } = useAuthStore();

    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const photoUrl = user?.profile_photo
        ? `${API_URL}/${user.profile_photo}`
        : null;

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6">
                {/* Page Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-white tracking-tight">User Profile</h1>
                        <p className="text-slate-400 mt-1">Manage your account settings, skills, and preferences</p>
                    </div>
                </div>

                {/* Tab Navigation */}
                <div className="flex items-center gap-1 bg-slate-900/50 border border-slate-800 rounded-xl p-1 w-fit">
                    {TABS.map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setActiveTab(id)}
                            className={cn(
                                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                                activeTab === id
                                    ? 'bg-primary/15 text-primary shadow-sm'
                                    : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
                            )}
                        >
                            <Icon className="h-4 w-4" />
                            {label}
                        </button>
                    ))}
                </div>

                {/* ═══════ PROFILE TAB ═══════ */}
                {activeTab === 'profile' && (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 max-w-6xl">
                        {/* Left: Avatar & Quick Stats */}
                        <div className="space-y-6">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs overflow-hidden">
                                <CardContent className="pt-8 flex flex-col items-center">
                                    <div className="relative group">
                                        <div className="h-32 w-32 rounded-full border-4 border-slate-800 bg-slate-800 flex items-center justify-center overflow-hidden">
                                            {photoUrl ? (
                                                <img src={photoUrl} alt={user?.full_name || ''} className="h-full w-full object-cover" />
                                            ) : (
                                                <span className="text-4xl font-bold text-slate-500 uppercase">
                                                    {user?.full_name?.slice(0, 2) || user?.username?.slice(0, 2)}
                                                </span>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => fileInputRef.current?.click()}
                                            className="absolute bottom-0 right-0 p-2 rounded-full bg-purple-600 text-white hover:bg-purple-700 transition-colors shadow-lg"
                                            disabled={uploadPhoto.isPending}
                                        >
                                            {uploadPhoto.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
                                        </button>
                                        <input
                                            type="file"
                                            ref={fileInputRef}
                                            className="hidden"
                                            accept="image/*"
                                            onChange={handlePhotoUpload}
                                        />
                                    </div>
                                    <h2 className="mt-4 text-xl font-bold text-white">{user?.full_name}</h2>
                                    <p className="text-slate-500 text-sm">@{user?.username}</p>
                                    <div className="mt-2 text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 uppercase font-bold tracking-wider">
                                        {user?.role}
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Right: Forms */}
                        <div className="lg:col-span-2 space-y-6">
                            {/* Profile Info Form */}
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader>
                                    <CardTitle className="text-white flex items-center gap-2 text-lg">
                                        <User className="h-5 w-5 text-purple-500" />
                                        General Information
                                    </CardTitle>
                                    <CardDescription>Update your personal details and email address</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <form onSubmit={handleProfileSubmit} className="space-y-4">
                                        {profileMessage && (
                                            <Alert className={cn(
                                                "border",
                                                profileMessage.type === 'success' ? "border-green-500/20 bg-green-500/10 text-green-400" : "border-red-500/20 bg-red-500/10 text-red-400"
                                            )}>
                                                {profileMessage.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                                                <AlertTitle>{profileMessage.type === 'success' ? 'Success' : 'Error'}</AlertTitle>
                                                <AlertDescription>{profileMessage.text}</AlertDescription>
                                            </Alert>
                                        )}

                                        <div className="space-y-2">
                                            <Label htmlFor="full_name" className="text-slate-300">Full Name</Label>
                                            <div className="relative">
                                                <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                                <Input
                                                    id="full_name"
                                                    value={profileData.full_name}
                                                    onChange={(e) => setProfileData({ ...profileData, full_name: e.target.value })}
                                                    className="bg-slate-950/50 border-slate-700 pl-10 text-white focus:border-purple-500 transition-colors"
                                                    placeholder="Your full name"
                                                />
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <Label htmlFor="email" className="text-slate-300">Email Address</Label>
                                            <div className="relative">
                                                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                                                <Input
                                                    id="email"
                                                    type="email"
                                                    value={profileData.email}
                                                    onChange={(e) => setProfileData({ ...profileData, email: e.target.value })}
                                                    className="bg-slate-950/50 border-slate-700 pl-10 text-white focus:border-purple-500 transition-colors"
                                                    placeholder="your@email.com"
                                                    required
                                                    disabled={!isLocalUser}
                                                />
                                            </div>
                                            {!isLocalUser && (
                                                <p className="text-xs text-slate-500">
                                                    Email is managed by your identity provider ({user?.auth_provider?.toUpperCase()}).
                                                </p>
                                            )}
                                        </div>

                                        {emailChanged && isLocalUser && (
                                            <div className="space-y-2 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                                                <p className="text-xs text-amber-300">
                                                    Email is your password-reset address. Re-confirm your identity to change it — all sessions will be revoked.
                                                </p>
                                                <Input
                                                    type="password"
                                                    placeholder="Current password"
                                                    value={emailChangePassword}
                                                    onChange={(e) => setEmailChangePassword(e.target.value)}
                                                    className="bg-slate-950/50 border-slate-700 text-white"
                                                    autoComplete="current-password"
                                                />
                                                {user?.totp_enabled && (
                                                    <Input
                                                        type="text"
                                                        inputMode="numeric"
                                                        placeholder="6-digit 2FA code"
                                                        value={emailChangeTotpCode}
                                                        onChange={(e) => setEmailChangeTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                                        maxLength={6}
                                                        className="bg-slate-950/50 border-slate-700 text-white font-mono tracking-widest"
                                                    />
                                                )}
                                            </div>
                                        )}

                                        <Button
                                            type="submit"
                                            className="w-full bg-primary hover:bg-primary/90"
                                            disabled={
                                                updateProfile.isPending ||
                                                (emailChanged && isLocalUser && !emailChangePassword) ||
                                                (emailChanged && isLocalUser && !!user?.totp_enabled && emailChangeTotpCode.length !== 6)
                                            }
                                        >
                                            {updateProfile.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                            Save Changes
                                        </Button>
                                    </form>
                                </CardContent>
                            </Card>

                            {/* Appearance / Theme Picker */}
                            <AppearanceCard />

                            {/* Password Change Form */}
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader>
                                    <CardTitle className="text-white flex items-center gap-2 text-lg">
                                        <Lock className="h-5 w-5 text-amber-500" />
                                        Change Password
                                    </CardTitle>
                                    <CardDescription>Update your password to keep your account secure</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <form onSubmit={handlePasswordSubmit} className="space-y-4">
                                        {passwordMessage && (
                                            <Alert className={cn(
                                                "border",
                                                passwordMessage.type === 'success' ? "border-green-500/20 bg-green-500/10 text-green-400" : "border-red-500/20 bg-red-500/10 text-red-400"
                                            )}>
                                                {passwordMessage.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                                                <AlertTitle>{passwordMessage.type === 'success' ? 'Success' : 'Error'}</AlertTitle>
                                                <AlertDescription>{passwordMessage.text}</AlertDescription>
                                            </Alert>
                                        )}

                                        <div className="space-y-2">
                                            <Label htmlFor="old_password" className="text-slate-300">Current Password</Label>
                                            <Input
                                                id="old_password"
                                                type="password"
                                                value={passwordData.old_password}
                                                onChange={(e) => setPasswordData({ ...passwordData, old_password: e.target.value })}
                                                className="bg-slate-950/50 border-slate-700 text-white focus:border-amber-500 transition-colors"
                                                required
                                            />
                                        </div>

                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <Label htmlFor="new_password" className="text-slate-300">New Password</Label>
                                                <Input
                                                    id="new_password"
                                                    type="password"
                                                    value={passwordData.new_password}
                                                    onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                                                    className="bg-slate-950/50 border-slate-700 text-white focus:border-amber-500 transition-colors"
                                                    required
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <Label htmlFor="confirm_password" className="text-slate-300">Confirm Password</Label>
                                                <Input
                                                    id="confirm_password"
                                                    type="password"
                                                    value={passwordData.confirm_password}
                                                    onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
                                                    className="bg-slate-950/50 border-slate-700 text-white focus:border-amber-500 transition-colors"
                                                    required
                                                />
                                            </div>
                                        </div>
                                        {user?.totp_enabled && (
                                            <div className="space-y-2">
                                                <Label htmlFor="totp_code" className="text-slate-300">2FA Code</Label>
                                                <Input
                                                    id="totp_code"
                                                    type="text"
                                                    inputMode="numeric"
                                                    autoComplete="one-time-code"
                                                    maxLength={6}
                                                    placeholder="123456"
                                                    value={passwordData.totp_code}
                                                    onChange={(e) => setPasswordData({ ...passwordData, totp_code: e.target.value.replace(/\D/g, '') })}
                                                    className="bg-slate-950/50 border-slate-700 text-white focus:border-amber-500 transition-colors tracking-[0.4em] text-center"
                                                    required
                                                />
                                                <p className="text-xs text-slate-500">Enter the 6-digit code from your authenticator app.</p>
                                            </div>
                                        )}
                                        {wordlistChecking && (
                                            <p className="text-xs text-slate-500 flex items-center gap-1">
                                                <Loader2 className="h-3 w-3 animate-spin" /> Checking against wordlists…
                                            </p>
                                        )}
                                        {wordlistWarning && !wordlistChecking && (
                                            <div className="flex items-start gap-2 p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
                                                <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                                                <p className="text-xs text-amber-400">
                                                    This password appears in a known breach wordlist. Consider using a stronger password.
                                                </p>
                                            </div>
                                        )}

                                        <Button
                                            type="submit"
                                            className="w-full bg-slate-800 hover:bg-slate-700 text-white border border-slate-700"
                                            disabled={updatePassword.isPending}
                                        >
                                            {updatePassword.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                            Update Password
                                        </Button>
                                    </form>
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                )}

                {/* ═══════ SKILLS TAB ═══════ */}
                {activeTab === 'skills' && (
                    <SkillsTab userId={user?.id} />
                )}

                {/* ═══════ SECURITY TAB ═══════ */}
                {activeTab === 'security' && (
                    <div className="max-w-3xl space-y-6">
                        {/* Two-Factor Authentication */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader>
                                <CardTitle className="text-white flex items-center gap-2 text-lg">
                                    <Shield className="h-5 w-5 text-emerald-500" />
                                    Two-Factor Authentication
                                </CardTitle>
                                <CardDescription>Add an extra layer of security with an authenticator app</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {user?.totp_enabled ? (
                                    /* 2FA is enabled */
                                    <>
                                        <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                                            <ShieldCheck className="h-5 w-5 text-emerald-500" />
                                            <div>
                                                <p className="text-sm font-medium text-emerald-400">Two-factor authentication is enabled</p>
                                                <p className="text-xs text-slate-400">Your account is protected with an authenticator app</p>
                                            </div>
                                        </div>

                                        {showDisable ? (
                                            <div className="space-y-3 p-4 rounded-lg border border-red-500/20 bg-red-500/5">
                                                <p className="text-sm text-slate-300">To disable 2FA, enter your password and a current TOTP code:</p>
                                                <div className="space-y-2">
                                                    <Input
                                                        type="password"
                                                        placeholder="Current password"
                                                        value={disablePassword}
                                                        onChange={(e) => setDisablePassword(e.target.value)}
                                                        className="bg-slate-950/50 border-slate-700 text-white"
                                                    />
                                                    <Input
                                                        type="text"
                                                        inputMode="numeric"
                                                        placeholder="6-digit code"
                                                        value={disableCode}
                                                        onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                                        maxLength={6}
                                                        className="bg-slate-950/50 border-slate-700 text-white font-mono tracking-widest"
                                                    />
                                                </div>
                                                <div className="flex gap-2">
                                                    <Button
                                                        variant="destructive"
                                                        onClick={handleTotpDisable}
                                                        disabled={totpLoading || disableCode.length !== 6 || !disablePassword}
                                                        className="flex-1"
                                                    >
                                                        {totpLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                                        Disable 2FA
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        onClick={() => { setShowDisable(false); setDisablePassword(''); setDisableCode(''); }}
                                                        className="text-slate-400"
                                                    >
                                                        Cancel
                                                    </Button>
                                                </div>
                                            </div>
                                        ) : (
                                            <Button
                                                variant="ghost"
                                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                                onClick={() => setShowDisable(true)}
                                            >
                                                <ShieldOff className="h-4 w-4 mr-2" />
                                                Disable Two-Factor Authentication
                                            </Button>
                                        )}

                                        {/* Recovery codes — show remaining count + regen affordance */}
                                        <div className="pt-4 mt-4 border-t border-slate-800/60">
                                            <div className="flex items-start justify-between gap-4 mb-3">
                                                <div>
                                                    <p className="text-sm font-medium text-white">Recovery Codes</p>
                                                    <p className="text-xs text-slate-400 mt-0.5">
                                                        Single-use codes for self-service recovery if you lose your authenticator.
                                                    </p>
                                                </div>
                                                <div className="text-right shrink-0">
                                                    <p className={cn(
                                                        'text-2xl font-bold font-mono',
                                                        (user?.recovery_codes_remaining ?? 0) <= 3
                                                            ? 'text-amber-400'
                                                            : 'text-slate-200',
                                                    )}>
                                                        {user?.recovery_codes_remaining ?? 0}
                                                    </p>
                                                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">Remaining</p>
                                                </div>
                                            </div>
                                            {(user?.recovery_codes_remaining ?? 0) <= 3 && (
                                                <div className="flex items-center gap-2 p-2 mb-3 rounded-md bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
                                                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                                    <span>You're running low. Regenerate to get 10 fresh codes (the old set will be invalidated).</span>
                                                </div>
                                            )}
                                            {showRegenerate ? (
                                                <div className="space-y-3 p-4 rounded-lg border border-amber-500/20 bg-amber-500/5">
                                                    <p className="text-sm text-slate-300">
                                                        Regenerating issues 10 new codes and invalidates your existing set.
                                                        Enter your password and a current TOTP code:
                                                    </p>
                                                    <div className="space-y-2">
                                                        <Input
                                                            type="password"
                                                            placeholder="Current password"
                                                            value={regeneratePassword}
                                                            onChange={(e) => setRegeneratePassword(e.target.value)}
                                                            className="bg-slate-950/50 border-slate-700 text-white"
                                                        />
                                                        <Input
                                                            type="text"
                                                            inputMode="numeric"
                                                            placeholder="6-digit TOTP code"
                                                            value={regenerateCode}
                                                            onChange={(e) => setRegenerateCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                                            maxLength={6}
                                                            className="bg-slate-950/50 border-slate-700 text-white font-mono tracking-widest"
                                                        />
                                                    </div>
                                                    <div className="flex gap-2">
                                                        <Button
                                                            onClick={handleRegenerateCodes}
                                                            disabled={regenerateLoading || regenerateCode.length !== 6 || !regeneratePassword}
                                                            className="flex-1 bg-amber-600 hover:bg-amber-500 text-white"
                                                        >
                                                            {regenerateLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                                            Regenerate Codes
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            onClick={() => { setShowRegenerate(false); setRegeneratePassword(''); setRegenerateCode(''); }}
                                                            className="text-slate-400"
                                                        >
                                                            Cancel
                                                        </Button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <Button
                                                    variant="ghost"
                                                    className="text-amber-400 hover:text-amber-300 hover:bg-amber-500/10"
                                                    onClick={() => setShowRegenerate(true)}
                                                >
                                                    <RefreshCw className="h-4 w-4 mr-2" />
                                                    Regenerate Recovery Codes
                                                </Button>
                                            )}
                                        </div>
                                    </>
                                ) : totpSetup ? (
                                    /* Setup in progress */
                                    <div className="space-y-4">
                                        <p className="text-sm text-slate-300">
                                            Scan this QR code with your authenticator app (Google Authenticator, Duo Mobile, Authy, etc.):
                                        </p>
                                        <div className="flex justify-center">
                                            <div className="p-3 bg-white rounded-xl">
                                                <img src={totpSetup.qr_code} alt="TOTP QR Code" className="h-48 w-48" />
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between">
                                                <Label className="text-slate-400 text-xs">Manual entry key</Label>
                                                <div className="flex gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => setShowSecret(!showSecret)}
                                                        className="h-6 px-2 text-slate-500 hover:text-slate-300"
                                                    >
                                                        {showSecret ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => { navigator.clipboard.writeText(totpSetup.secret); toast.success('Secret copied!'); }}
                                                        className="h-6 px-2 text-slate-500 hover:text-slate-300"
                                                    >
                                                        <Copy className="h-3 w-3" />
                                                    </Button>
                                                </div>
                                            </div>
                                            <code className="block w-full p-2 rounded bg-slate-950/80 border border-slate-700 text-amber-400 font-mono text-sm text-center tracking-wider">
                                                {showSecret ? totpSetup.secret : '••••••••••••••••'}
                                            </code>
                                        </div>

                                        <div className="space-y-2">
                                            <Label className="text-slate-300">Enter the 6-digit code from your app to verify:</Label>
                                            <Input
                                                type="text"
                                                inputMode="numeric"
                                                placeholder="000000"
                                                value={totpCode}
                                                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                                maxLength={6}
                                                className="bg-slate-950/50 border-slate-700 text-white text-center text-xl font-mono tracking-[0.5em]"
                                            />
                                        </div>

                                        <div className="flex gap-2">
                                            <Button
                                                onClick={handleTotpVerify}
                                                disabled={totpLoading || totpCode.length !== 6}
                                                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                                            >
                                                {totpLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                                Verify & Enable
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                onClick={() => { setTotpSetup(null); setTotpCode(''); setShowSecret(false); }}
                                                className="text-slate-400"
                                            >
                                                Cancel
                                            </Button>
                                        </div>
                                    </div>
                                ) : user?.auth_provider && user.auth_provider !== 'local' ? (
                                    /* SSO / LDAP — 2FA managed by the identity provider */
                                    <div className="space-y-2 text-sm text-slate-400">
                                        <p>Two-factor authentication is managed by your identity provider ({user.auth_provider.toUpperCase()}).</p>
                                        <p>Configure MFA there to apply it to this account.</p>
                                    </div>
                                ) : showSetupPrompt ? (
                                    /* Setup password prompt — gates /totp/setup so a stolen session alone can't bind 2FA */
                                    <div className="space-y-3 p-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
                                        <p className="text-sm text-slate-300">Enter your current password to begin 2FA setup:</p>
                                        <Input
                                            type="password"
                                            placeholder="Current password"
                                            value={setupPassword}
                                            onChange={(e) => setSetupPassword(e.target.value)}
                                            onKeyDown={(e) => { if (e.key === 'Enter' && setupPassword) handleTotpSetup(); }}
                                            className="bg-slate-950/50 border-slate-700 text-white"
                                            autoFocus
                                        />
                                        <div className="flex gap-2">
                                            <Button
                                                onClick={handleTotpSetup}
                                                disabled={totpLoading || !setupPassword}
                                                className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                                            >
                                                {totpLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                                Continue
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                onClick={() => { setShowSetupPrompt(false); setSetupPassword(''); }}
                                                className="text-slate-400"
                                            >
                                                Cancel
                                            </Button>
                                        </div>
                                    </div>
                                ) : (
                                    /* Not enabled, show setup button */
                                    <div className="space-y-3">
                                        <p className="text-sm text-slate-400">
                                            Protect your account with time-based one-time passwords (TOTP). Compatible with Google Authenticator, Duo Mobile, Authy, and more.
                                        </p>
                                        <Button
                                            onClick={() => setShowSetupPrompt(true)}
                                            disabled={totpLoading}
                                            className="bg-emerald-600 hover:bg-emerald-700"
                                        >
                                            {totpLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Shield className="h-4 w-4 mr-2" />}
                                            Set Up Two-Factor Authentication
                                        </Button>
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* API Tokens */}
                        <ApiTokensCard />
                    </div>
                )}

                {/* ═══════ NOTIFICATIONS TAB ═══════ */}
                {activeTab === 'notifications' && (
                    <div className="max-w-3xl">
                        <NotificationSettingsCard />
                    </div>
                )}
            </div>

            {/* ═══════ RECOVERY CODES MODAL ═══════ */}
            {/* Shown once after 2FA enrollment or regeneration. Blocks until
                the user acknowledges they've saved the codes. Plaintext is
                never re-fetchable from the server. GHSA-vm6w-9wm5-q367. */}
            {recoveryCodes && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
                    <div className="w-full max-w-lg rounded-xl border-2 border-amber-500/60 bg-slate-950 shadow-2xl overflow-hidden">
                        <div className="bg-amber-500/10 border-b border-amber-500/30 px-5 py-3 flex items-center gap-3">
                            <Shield className="w-5 h-5 text-amber-400 shrink-0" />
                            <span className="text-sm font-semibold text-amber-400">
                                Save your 2FA recovery codes
                            </span>
                        </div>
                        <div className="px-5 py-4 space-y-4">
                            <p className="text-sm text-slate-300 leading-relaxed">
                                These <strong>{recoveryCodes.length}</strong> single-use codes are your
                                self-service recovery path if you lose your authenticator. Save them
                                somewhere safe (password manager, printed and locked away).
                                <br />
                                <span className="text-amber-300 font-medium">You won't see them again.</span>
                            </p>
                            <div className="grid grid-cols-2 gap-2 p-4 rounded-lg bg-slate-900/80 border border-slate-800 font-mono text-sm">
                                {recoveryCodes.map((code) => (
                                    <div
                                        key={code}
                                        className="text-center text-slate-200 select-all py-1.5 rounded bg-slate-950/60 border border-slate-800/60"
                                    >
                                        {code}
                                    </div>
                                ))}
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    type="button"
                                    onClick={handleCopyAllCodes}
                                    className="flex-1 bg-slate-800 hover:bg-slate-700 text-white"
                                >
                                    <Copy className="h-4 w-4 mr-2" /> Copy All
                                </Button>
                                <Button
                                    type="button"
                                    onClick={handleDownloadCodes}
                                    className="flex-1 bg-slate-800 hover:bg-slate-700 text-white"
                                >
                                    <Download className="h-4 w-4 mr-2" /> Download .txt
                                </Button>
                            </div>
                            <label className="flex items-start gap-2 cursor-pointer pt-2 border-t border-slate-800/60">
                                <input
                                    type="checkbox"
                                    checked={recoveryAcknowledged}
                                    onChange={(e) => setRecoveryAcknowledged(e.target.checked)}
                                    className="mt-1 accent-amber-500"
                                />
                                <span className="text-xs text-slate-300">
                                    I've saved these codes somewhere safe. I understand they
                                    won't be shown again, and that each code can be used at
                                    most once.
                                </span>
                            </label>
                            <Button
                                type="button"
                                disabled={!recoveryAcknowledged}
                                onClick={() => { setRecoveryCodes(null); setRecoveryAcknowledged(false); }}
                                className="w-full bg-amber-600 hover:bg-amber-500 text-white disabled:bg-slate-800 disabled:text-slate-500"
                            >
                                Done
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </DashboardLayout>
    );
}


// ═══════════════════════════════════════════════════════════════════
//  APPEARANCE CARD — Palette + Accent picker
// ═══════════════════════════════════════════════════════════════════

// Swatch colors are HARDCODED hex (not slate/named utilities) so each preview
// shows its own palette regardless of the currently-active theme.
const PALETTE_SWATCHES: { id: ThemePalette; label: string; preview: string; ring: string; description: string }[] = [
    { id: 'aurora',    label: 'Aurora',    preview: 'bg-linear-to-br from-[#1e293b] to-[#020617]', ring: 'ring-slate-400',  description: 'Modern and professional — cool navy surfaces' },
    { id: 'operator',  label: 'Operator',  preview: 'bg-linear-to-br from-[#0c0c10] to-[#060608]', ring: 'ring-red-500/60', description: 'Login-inspired — near-black with subtle red warmth' },
    { id: 'half-dark', label: 'Half Dark', preview: 'bg-linear-to-br from-[#1f2329] to-[#282c34]', ring: 'ring-blue-300/60', description: 'Windows Terminal "One Half Dark" — desaturated indigo' },
    { id: 'light',     label: 'Light',     preview: 'bg-linear-to-br from-[#ffffff] to-[#f1f5f9]', ring: 'ring-slate-700/60', description: 'Bright surfaces with dark text' },
];

const ACCENT_SWATCHES: { id: ThemePreference; label: string; ring: string; swatch: string; description: string }[] = [
    { id: 'purple',  label: 'Purple',  ring: 'ring-purple-500',  swatch: 'bg-purple-600',  description: 'Calm and balanced (default)' },
    { id: 'crimson', label: 'Crimson', ring: 'ring-red-500',     swatch: 'bg-red-600',     description: 'High-energy operator red' },
    { id: 'blue',    label: 'Blue',    ring: 'ring-blue-500',    swatch: 'bg-blue-500',    description: 'Classic and clear' },
    { id: 'emerald', label: 'Emerald', ring: 'ring-emerald-500', swatch: 'bg-emerald-500', description: 'Fresh and operational' },
    { id: 'amber',   label: 'Amber',   ring: 'ring-amber-500',   swatch: 'bg-amber-500',   description: 'Warm and bright' },
];

function AppearanceCard() {
    const { user } = useAuthStore();
    const updateProfile = useUpdateProfile();
    const currentAccent: ThemePreference = (user?.theme_preference as ThemePreference) || 'purple';
    const currentPalette: ThemePalette = (user?.theme_palette as ThemePalette) || 'aurora';
    const currentCustom: string = user?.theme_accent_custom || '#a855f7';

    // Local state for the color input so dragging the picker doesn't fire a
    // PUT on every pixel change. Commit on blur / native `change` event.
    const [pendingCustom, setPendingCustom] = useState<string>(currentCustom);
    useEffect(() => { setPendingCustom(currentCustom); }, [currentCustom]);

    const pickAccent = async (accent: ThemePreference) => {
        if (accent === currentAccent || updateProfile.isPending) return;
        const label = ACCENT_SWATCHES.find(t => t.id === accent)?.label ?? (accent === 'custom' ? 'Custom' : accent);
        try {
            // Picking 'custom' for the first time: ensure a hex is on file
            const payload: any = { theme_preference: accent };
            if (accent === 'custom' && !user?.theme_accent_custom) {
                payload.theme_accent_custom = pendingCustom;
            }
            await updateProfile.mutateAsync(payload);
            toast.success(`Accent set to ${label}`);
        } catch (err: any) {
            toast.error(err?.response?.data?.detail || 'Failed to update accent');
        }
    };

    const commitCustom = async (hex: string) => {
        if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;
        if (hex === currentCustom && currentAccent === 'custom') return;
        try {
            await updateProfile.mutateAsync({ theme_preference: 'custom', theme_accent_custom: hex });
        } catch (err: any) {
            toast.error(err?.response?.data?.detail || 'Failed to update custom accent');
        }
    };

    const pickPalette = async (palette: ThemePalette) => {
        if (palette === currentPalette || updateProfile.isPending) return;
        const label = PALETTE_SWATCHES.find(t => t.id === palette)?.label ?? palette;
        try {
            await updateProfile.mutateAsync({ theme_palette: palette });
            toast.success(`Palette set to ${label}`);
        } catch (err: any) {
            toast.error(err?.response?.data?.detail || 'Failed to update palette');
        }
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
            <CardHeader>
                <CardTitle className="text-white flex items-center gap-2 text-lg">
                    <Palette className="h-5 w-5 text-primary" />
                    Appearance
                </CardTitle>
                <CardDescription>Palette controls surface colors; accent controls action colors. Mix freely.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* ── Palette ── */}
                <div>
                    <h4 className="text-xs uppercase tracking-wider font-semibold text-slate-400 mb-3">Palette</h4>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {PALETTE_SWATCHES.map(p => {
                            const isActive = currentPalette === p.id;
                            return (
                                <button
                                    key={p.id}
                                    type="button"
                                    onClick={() => pickPalette(p.id)}
                                    disabled={updateProfile.isPending}
                                    className={cn(
                                        'group relative flex flex-col items-start gap-2 p-3 rounded-lg border transition-all text-left',
                                        isActive
                                            ? 'border-slate-700 bg-slate-800/60 ring-2 ring-offset-2 ring-offset-slate-900'
                                            : 'border-slate-800 hover:border-slate-700 hover:bg-slate-800/40',
                                        isActive && p.ring,
                                    )}
                                >
                                    <div className={cn('h-10 w-full rounded-md shadow-inner border border-white/5', p.preview)} />
                                    <div className="flex items-center gap-1.5 w-full">
                                        <span className="text-sm font-medium text-white">{p.label}</span>
                                        {isActive && <Check className="h-3.5 w-3.5 text-white ml-auto" />}
                                    </div>
                                    <span className="text-[11px] text-slate-500 leading-tight">{p.description}</span>
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* ── Accent ── */}
                <div>
                    <h4 className="text-xs uppercase tracking-wider font-semibold text-slate-400 mb-3">Accent</h4>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        {ACCENT_SWATCHES.map(t => {
                            const isActive = currentAccent === t.id;
                            return (
                                <button
                                    key={t.id}
                                    type="button"
                                    onClick={() => pickAccent(t.id)}
                                    disabled={updateProfile.isPending}
                                    className={cn(
                                        'group relative flex flex-col items-start gap-2 p-3 rounded-lg border transition-all text-left',
                                        isActive
                                            ? 'border-slate-700 bg-slate-800/60 ring-2 ring-offset-2 ring-offset-slate-900'
                                            : 'border-slate-800 hover:border-slate-700 hover:bg-slate-800/40',
                                        isActive && t.ring,
                                    )}
                                >
                                    <div className={cn('h-10 w-full rounded-md shadow-inner', t.swatch)} />
                                    <div className="flex items-center gap-1.5 w-full">
                                        <span className="text-sm font-medium text-white">{t.label}</span>
                                        {isActive && <Check className="h-3.5 w-3.5 text-white ml-auto" />}
                                    </div>
                                    <span className="text-[11px] text-slate-500 leading-tight">{t.description}</span>
                                </button>
                            );
                        })}

                        {/* Custom — color wheel input */}
                        <div
                            className={cn(
                                'group relative flex flex-col items-start gap-2 p-3 rounded-lg border transition-all text-left',
                                currentAccent === 'custom'
                                    ? 'border-slate-700 bg-slate-800/60 ring-2 ring-offset-2 ring-offset-slate-900'
                                    : 'border-slate-800 hover:border-slate-700 hover:bg-slate-800/40',
                                currentAccent === 'custom' && 'ring-white/40',
                            )}
                        >
                            <label
                                htmlFor="custom-accent-color"
                                className="h-10 w-full rounded-md shadow-inner cursor-pointer relative overflow-hidden block"
                                style={{ backgroundColor: pendingCustom }}
                                title="Click to choose any color"
                            >
                                <input
                                    id="custom-accent-color"
                                    type="color"
                                    value={pendingCustom}
                                    onChange={(e) => setPendingCustom(e.target.value)}
                                    onBlur={(e) => commitCustom(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Enter') commitCustom((e.target as HTMLInputElement).value); }}
                                    className="absolute inset-0 opacity-0 cursor-pointer"
                                    aria-label="Custom accent color"
                                />
                            </label>
                            <div className="flex items-center gap-1.5 w-full">
                                <span className="text-sm font-medium text-white">Custom</span>
                                {currentAccent === 'custom' && <Check className="h-3.5 w-3.5 text-white ml-auto" />}
                            </div>
                            <button
                                type="button"
                                onClick={() => commitCustom(pendingCustom)}
                                className="text-[11px] text-slate-500 leading-tight font-mono hover:text-slate-300 transition-colors"
                                title="Click to apply"
                            >
                                {pendingCustom.toUpperCase()}
                            </button>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}


// ═══════════════════════════════════════════════════════════════════
//  SKILLS TAB
// ═══════════════════════════════════════════════════════════════════

function SkillsTab({ userId }: { userId: string | undefined }) {
    const { data: categories = [], isLoading: catsLoading } = useSkillCategories();
    const { data: userSkills = [], isLoading: skillsLoading } = useUserSkills(userId);
    const { data: averageSkills = [] } = useAverageSkills();
    const setMySkills = useSetMySkills();

    // Local state for editing skill levels
    const [localLevels, setLocalLevels] = useState<Record<string, number>>({});
    const [localTargets, setLocalTargets] = useState<Record<string, number | null>>({});
    const [hasChanges, setHasChanges] = useState(false);

    // Initialize local state from fetched data
    useEffect(() => {
        const lvl: Record<string, number> = {};
        const tgt: Record<string, number | null> = {};
        userSkills.forEach((us) => {
            lvl[us.skill_id] = us.level;
            tgt[us.skill_id] = us.target_level ?? null;
        });
        setLocalLevels(lvl);
        setLocalTargets(tgt);
        setHasChanges(false);
    }, [userSkills]);

    const focusCount = useMemo(
        () => Object.values(localTargets).filter((t) => t !== null && t !== undefined).length,
        [localTargets],
    );
    const focusCapReached = focusCount >= MAX_GROWTH_FOCUSES;

    const setLevel = (skillId: string, level: number) => {
        setLocalLevels((prev) => ({ ...prev, [skillId]: level }));
        setLocalTargets((prev) => {
            const target = prev[skillId];
            // Auto-clear stale target when level catches up, or when reaching max.
            if (target != null && (level >= target || level >= 3)) {
                return { ...prev, [skillId]: null };
            }
            return prev;
        });
        setHasChanges(true);
    };

    const toggleFocus = (skillId: string) => {
        setLocalTargets((prev) => {
            const current = prev[skillId];
            if (current != null) {
                return { ...prev, [skillId]: null };
            }
            const level = localLevels[skillId] ?? 0;
            if (level >= 3) return prev;
            const activeFocuses = Object.values(prev).filter((t) => t !== null && t !== undefined).length;
            if (activeFocuses >= MAX_GROWTH_FOCUSES) {
                toast.error(`You can focus on at most ${MAX_GROWTH_FOCUSES} skills at a time`);
                return prev;
            }
            return { ...prev, [skillId]: level + 1 };
        });
        setHasChanges(true);
    };

    const handleSave = async () => {
        const skills = Object.entries(localLevels).map(([skill_id, level]) => ({
            skill_id,
            level,
            target_level: localTargets[skill_id] ?? null,
        }));
        try {
            await setMySkills.mutateAsync(skills);
            toast.success('Skills updated successfully');
            setHasChanges(false);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to save skills');
        }
    };

    // Build category-grouped radar data
    const { radarData, labelColors, anyTargetSet } = useMemo(() => {
        if (!categories.length) return { radarData: [], labelColors: {}, anyTargetSet: false };
        const avgMap: Record<string, number> = {};
        averageSkills.forEach((s) => { avgMap[s.skill_id] = s.level; });

        const result = buildCategoryRadarData(categories, localLevels, avgMap, localTargets);
        const hasAny = result.data.some((d: any) => d.hasAnyTarget);
        return { radarData: result.data, labelColors: result.labelColors, anyTargetSet: hasAny };
    }, [categories, localLevels, averageSkills, localTargets]);

    const isLoading = catsLoading || skillsLoading;

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
            </div>
        );
    }

    if (categories.length === 0) {
        return (
            <Card className="border-slate-800 bg-slate-900/50 max-w-3xl">
                <CardContent className="py-12 text-center">
                    <Radar className="h-12 w-12 text-slate-700 mx-auto mb-3" />
                    <p className="text-slate-400">No skill categories configured yet.</p>
                    <p className="text-xs text-slate-600 mt-1">Ask an admin to set up skill categories and skills.</p>
                </CardContent>
            </Card>
        );
    }

    const radarSeries = [
        { key: 'level', label: 'My Skills', color: '#a855f7', fillOpacity: 0.2 },
        { key: 'average', label: 'Team Average', color: '#64748b', fillOpacity: 0, strokeDasharray: '4 3' },
        // Only render the growth-goal series when at least one skill has a
        // target — otherwise it would just trace over the level line.
        ...(anyTargetSet
            ? [{ key: 'target', label: 'Growth Goals', color: '#22c55e', fillOpacity: 0.1, strokeDasharray: '5 3' }]
            : []),
    ];

    return (
        <div className="space-y-6 max-w-7xl">
            {/* Full-width Radar Chart */}
            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="text-white flex items-center gap-2 text-lg">
                                <Radar className="h-5 w-5 text-purple-500" />
                                Skill Profile
                            </CardTitle>
                            <CardDescription>Your proficiency overview vs. team average</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    {radarData.length > 0 ? (
                        <SkillsRadarChart
                            data={radarData}
                            series={radarSeries as any}
                            height={420}
                            hideLegend
                            labelColors={labelColors}
                        />
                    ) : (
                        <div className="flex flex-col items-center justify-center py-16">
                            <Radar className="h-16 w-16 text-slate-800 mb-3" />
                            <p className="text-sm text-slate-500 text-center">
                                Set your skill levels below to see your radar chart.
                            </p>
                        </div>
                    )}

                    {/* Legend */}
                    <div className="flex items-center justify-center gap-6 mt-4 pt-4 border-t border-slate-800">
                        <div className="flex items-center gap-1.5">
                            <div className="w-6 h-0.5 bg-purple-500 rounded" />
                            <span className="text-[11px] text-slate-400">My Skills</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <div className="w-6 h-0.5 border-t-2 border-dashed border-slate-500" />
                            <span className="text-[11px] text-slate-400">Team Average</span>
                        </div>
                        {anyTargetSet && (
                            <div className="flex items-center gap-1.5">
                                <div className="w-6 h-0.5 border-t-2 border-dashed border-green-500" />
                                <span className="text-[11px] text-slate-400">Growth Goals</span>
                            </div>
                        )}
                        <span className="text-[10px] text-slate-600 italic">Hover a category for skill breakdown</span>
                    </div>
                </CardContent>
            </Card>

            {/* Proficiency Selectors */}
            <div className="space-y-4">
                {/* Save button header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-wrap">
                        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
                            Set Your Proficiency
                        </h3>
                        <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
                            <Target className="h-3.5 w-3.5 text-purple-400" />
                            <span className={cn(focusCount > 0 && 'text-slate-300')}>
                                {focusCount} / {MAX_GROWTH_FOCUSES} growth focuses
                            </span>
                        </span>
                    </div>
                    <Button
                        onClick={handleSave}
                        disabled={!hasChanges || setMySkills.isPending}
                        className={cn(
                            'gap-2 transition-all',
                            hasChanges
                                ? 'bg-primary hover:bg-primary/90 text-white'
                                : 'bg-slate-800 text-slate-500'
                        )}
                        size="sm"
                    >
                        {setMySkills.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Save className="h-4 w-4" />
                        )}
                        Save Skills
                    </Button>
                </div>

                {categories.map((cat) => (
                    <Card key={cat.id} className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                        <CardHeader className="pb-3">
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <div
                                    className="w-3 h-3 rounded-full"
                                    style={{ backgroundColor: cat.color || '#6366f1' }}
                                />
                                {cat.name}
                                <span className="text-xs text-slate-600 font-normal">
                                    {cat.skills.length} skills
                                </span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {cat.skills.map((skill) => {
                                const level = localLevels[skill.id] ?? 0;
                                const target = localTargets[skill.id] ?? null;
                                const isFocused = target != null;
                                const canFocus = level < 3;
                                const focusDisabled = !canFocus || (!isFocused && focusCapReached);
                                return (
                                    <div
                                        key={skill.id}
                                        className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-800/40 transition-colors"
                                    >
                                        <div className="min-w-0 flex-1">
                                            <span className="text-sm text-white font-medium">{skill.name}</span>
                                            {skill.description && (
                                                <p className="text-xs text-slate-600 truncate">{skill.description}</p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-1 shrink-0 ml-4">
                                            {SKILL_LEVELS.map((lvl) => {
                                                const isActive = level === lvl.value;
                                                return (
                                                    <button
                                                        key={lvl.value}
                                                        onClick={() => setLevel(skill.id, lvl.value)}
                                                        className={cn(
                                                            'px-2.5 py-1 rounded-md text-xs font-medium transition-all border',
                                                            isActive
                                                                ? lvl.value === 0
                                                                    ? 'bg-slate-700 border-slate-600 text-slate-300'
                                                                    : lvl.value === 1
                                                                        ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                                                                        : lvl.value === 2
                                                                            ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                                                                            : 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                                                                : 'bg-transparent border-slate-800 text-slate-600 hover:text-slate-400 hover:border-slate-700'
                                                        )}
                                                    >
                                                        {lvl.label}
                                                    </button>
                                                );
                                            })}
                                            <TooltipProvider delayDuration={200}>
                                                <Tooltip>
                                                    <TooltipTrigger asChild>
                                                        <button
                                                            type="button"
                                                            onClick={() => !focusDisabled && toggleFocus(skill.id)}
                                                            disabled={focusDisabled}
                                                            aria-pressed={isFocused}
                                                            className={cn(
                                                                'ml-1 h-7 w-7 inline-flex items-center justify-center rounded-md border transition-all',
                                                                isFocused
                                                                    ? 'bg-primary/15 border-primary/40 text-primary'
                                                                    : focusDisabled
                                                                        ? 'border-slate-800/60 text-slate-700 cursor-not-allowed'
                                                                        : 'border-slate-800 text-slate-600 hover:text-primary hover:border-primary/30',
                                                            )}
                                                        >
                                                            <Target className={cn('h-3.5 w-3.5', isFocused && 'fill-current/20')} />
                                                        </button>
                                                    </TooltipTrigger>
                                                    <TooltipContent side="left" className="text-xs">
                                                        {isFocused
                                                            ? `Focus: growing toward ${SKILL_LEVELS[target]?.label} (click to remove)`
                                                            : !canFocus
                                                                ? 'Already at max proficiency'
                                                                : focusCapReached
                                                                    ? `Focus cap reached (${MAX_GROWTH_FOCUSES})`
                                                                    : `Focus on growing to ${SKILL_LEVELS[level + 1]?.label}`}
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                        </div>
                                    </div>
                                );
                            })}
                        </CardContent>
                    </Card>
                ))}
            </div>
        </div>
    );
}


// ═══════════════════════════════════════════════════════════════════
//  NOTIFICATION SETTINGS CARD
// ═══════════════════════════════════════════════════════════════════

function NotificationSettingsCard() {
    const { data: preferences = [], isLoading } = useNotificationPreferences();
    const updatePrefs = useUpdateNotificationPreferences();

    const handleToggle = (eventType: string, field: 'site_muted' | 'email_muted', currentValue: boolean) => {
        const updated = preferences.map((p) => ({
            event_type: p.event_type,
            site_muted: field === 'site_muted' && p.event_type === eventType ? !currentValue : p.site_muted,
            email_muted: field === 'email_muted' && p.event_type === eventType ? !currentValue : p.email_muted,
        }));
        updatePrefs.mutate(updated, {
            onSuccess: () => toast.success('Notification preferences saved'),
        });
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
            <CardHeader>
                <CardTitle className="text-white flex items-center gap-2 text-lg">
                    <BellRing className="h-5 w-5 text-blue-500" />
                    Notification Settings
                </CardTitle>
                <CardDescription>Choose which events you want to be notified about</CardDescription>
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <div className="flex justify-center py-6">
                        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                    </div>
                ) : (
                    <div className="space-y-1">
                        <div className="flex items-center text-xs text-slate-500 uppercase tracking-wider mb-3 px-1">
                            <span className="flex-1">Event</span>
                            <span className="w-20 text-center">Site</span>
                            <span className="w-20 text-center">Email</span>
                        </div>
                        {preferences.map((pref) => (
                            <div
                                key={pref.event_type}
                                className="flex items-center py-3 px-3 rounded-lg hover:bg-slate-800/30 transition-colors"
                            >
                                <div className="flex-1">
                                    <p className="text-sm font-medium text-white">{pref.label}</p>
                                    <p className="text-xs text-slate-500">{pref.event_type}</p>
                                </div>
                                <div className="w-20 flex justify-center">
                                    <Switch
                                        checked={!pref.site_muted}
                                        onCheckedChange={() => handleToggle(pref.event_type, 'site_muted', pref.site_muted)}
                                    />
                                </div>
                                <div className="w-20 flex justify-center">
                                    <TooltipProvider>
                                        <Tooltip>
                                            <TooltipTrigger asChild>
                                                <div>
                                                    <Switch
                                                        checked={!pref.email_muted}
                                                        disabled
                                                        className="opacity-40"
                                                    />
                                                </div>
                                            </TooltipTrigger>
                                            <TooltipContent>
                                                <p>Email notifications coming soon</p>
                                            </TooltipContent>
                                        </Tooltip>
                                    </TooltipProvider>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
