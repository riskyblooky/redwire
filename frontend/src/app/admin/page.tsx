/**
 * admin/page.tsx — Admin Console
 *
 * Centralised administration hub presented as a tabbed interface.
 * Tabs (selected via ?tab= query string):
 *  - Operators: user table with online/away/offline badges, group
 *    assignments, password resets, enable/disable, and deletion.
 *  - Permissions: delegated to `<PermissionsManagement>`.
 *  - Invite Codes: delegated to `<RegistrationCodeManagement>`.
 *  - Taxonomy: configurable types for engagements, findings, assets, etc.
 *  - Auth & Sessions: SSO, session timeout, MFA settings.
 *  - API Tokens: personal + service account token management.
 *  - Wordlists: uploaded wordlists for brute-force/dictionary ops.
 *  - AI Assistant: LLM provider & prompt configuration.
 *  - Skills: category/skill CRUD with colour-coded categories and a
 *    "Seed Default Skills" bootstrap action.
 *  - Widgets: dashboard widget management.
 *
 * The inline `SkillsAdminPanel` component handles category CRUD, skill
 * CRUD, colour pickers, inline editing, and the seed-defaults flow.
 */
'use client';

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAdminUsers, useUpdateUser, useDeleteUser, useResetPassword, useAdminConfig, useCreateUser } from '@/lib/hooks/use-admin';
import DashboardLayout from '@/components/layout/dashboard-layout';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Shield, Users, AlertTriangle, CheckCircle2, XCircle, MoreVertical, Trash2, Edit, UserMinus, UserCheck, Settings, Check, Key, Clock, Activity, Ticket, Layers, Lock, KeyRound, BookOpen, Brain, Radar, Plus, Loader2, LayoutGrid, Plug, Mail } from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { useAuthStore } from '@/stores/auth-store';
import { apiErrorMessage } from '@/lib/api';
import { format, formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { User, UserRole } from '@/lib/hooks/use-auth';
import { toast } from 'sonner';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { useGroups, Group } from '@/lib/hooks/use-admin-permissions';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useConfirmDialog, getErrorMessage } from '@/components/ui/confirm-dialog';

import { RegistrationCodeManagement } from '@/components/admin/registration-codes';
import { PermissionsManagement } from '@/components/admin/permissions-management';
import { StatsScopeSettings } from '@/components/admin/stats-scope-settings';
import { TypeManagement } from '@/components/admin/type-management';
import { AuthSettingsManagement } from '@/components/admin/auth-settings';
import { ApiTokenManagement } from '@/components/admin/api-token-management';
import { WordlistManagement } from '@/components/admin/wordlist-management';
import { AiSettingsManagement } from '@/components/admin/ai-settings';
import {
    useSkillCategories, useCreateSkillCategory, useUpdateSkillCategory, useDeleteSkillCategory,
    useCreateSkill, useUpdateSkill, useDeleteSkill, useSeedSkills,
    SKILL_LEVELS,
} from '@/lib/hooks/use-skills';
import type { SkillCategory, Skill } from '@/lib/hooks/use-skills';
import { WidgetManagement } from '@/components/admin/widget-management';
import { PluginManagement } from '@/components/admin/plugin-management';
import EmailSettings from '@/components/admin/email-settings';
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from '@/components/ui/tabs';

export default function AdminPage() {
    const searchParams = useSearchParams();
    const defaultTab = searchParams.get('tab') || 'users';
    const { data: users, isLoading: usersLoading } = useAdminUsers();
    const { data: groups, isLoading: groupsLoading } = useGroups();
    const { data: adminConfig } = useAdminConfig();
    const sessionTimeoutMinutes = (adminConfig?.session_timeout_hours ?? 24) * 60;

    const updateUser = useUpdateUser();
    const deleteUser = useDeleteUser();
    const resetPassword = useResetPassword();

    const createUser = useCreateUser();

    const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
    const [createForm, setCreateForm] = useState({
        username: '',
        email: '',
        password: '',
        full_name: '',
        role: UserRole.OPERATOR,
    });
    const [createFormError, setCreateFormError] = useState<string | null>(null);

    const handleCreateUser = async () => {
        setCreateFormError(null);
        if (!createForm.username || !createForm.email || !createForm.password) {
            setCreateFormError('Username, email, and password are required.');
            return;
        }
        try {
            await createUser.mutateAsync(createForm);
            toast.success(`User '${createForm.username}' created successfully`);
            setIsCreateDialogOpen(false);
            setCreateForm({ username: '', email: '', password: '', full_name: '', role: UserRole.OPERATOR });
        } catch (error: any) {
            setCreateFormError(apiErrorMessage(error, 'Failed to create user'));
        }
    };

    const { user: currentUser } = useAuthStore();
    const [selectedUser, setSelectedUser] = useState<User | null>(null);
    const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
    const [editForm, setEditForm] = useState<{
        isAdmin: boolean;
        isReadOnlyAdmin: boolean;
        groupIds: string[];
    }>({
        isAdmin: false,
        isReadOnlyAdmin: false,
        groupIds: []
    });
    const [tempPassword, setTempPassword] = useState<string | null>(null);
    const [isPasswordDialogOpen, setIsPasswordDialogOpen] = useState(false);
    const { confirm, ConfirmDialog } = useConfirmDialog();

    const handleEditClick = (user: User) => {
        const roleStr = user.role as string;
        const isReadOnlyAdmin = roleStr === UserRole.READ_ONLY_ADMIN;
        setSelectedUser(user);
        setEditForm({
            isAdmin: roleStr === UserRole.ADMIN || isReadOnlyAdmin,
            isReadOnlyAdmin,
            groupIds: (user as any).groups?.map((g: any) => g.id) || []
        });
        setIsEditDialogOpen(true);
    };

    const handleUpdateUser = async () => {
        if (!selectedUser) return;
        const role = editForm.isAdmin
            ? (editForm.isReadOnlyAdmin ? UserRole.READ_ONLY_ADMIN : UserRole.ADMIN)
            : UserRole.OPERATOR;
        try {
            await updateUser.mutateAsync({
                userId: selectedUser.id,
                data: {
                    role,
                    group_ids: editForm.groupIds
                } as any
            });
            toast.success('User updated successfully');
            setIsEditDialogOpen(false);
        } catch (error) {
            toast.error('Failed to update user');
        }
    };

    const handleStatusToggle = async (user: User) => {
        try {
            await updateUser.mutateAsync({
                userId: user.id,
                data: { is_active: !user.is_active }
            });
            toast.success(`User account ${!user.is_active ? 'enabled' : 'disabled'} successfully`);
        } catch (error) {
            toast.error('Failed to update user status');
        }
    };

    const handleDelete = async (userId: string) => {
        const confirmed = await confirm({
            title: 'Delete User',
            description: 'Are you sure you want to delete this user? This action cannot be undone.',
        });
        if (!confirmed) return;

        try {
            await deleteUser.mutateAsync(userId);
            toast.success('User deleted successfully');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to delete user'));
        }
    };

    const handleResetPassword = async (userId: string) => {
        const confirmed = await confirm({
            title: 'Reset Password',
            description: 'Are you sure you want to reset this user\'s password? A temporary one will be generated.',
            variant: 'warning',
            confirmLabel: 'Reset Password',
        });
        if (!confirmed) return;

        try {
            const result = await resetPassword.mutateAsync(userId);
            setTempPassword(result.temporary_password);
            setIsPasswordDialogOpen(true);
            toast.success('Password reset successfully');
        } catch (error: any) {
            toast.error(getErrorMessage(error, 'Failed to reset password'));
        }
    };



    if (usersLoading) {
        return (
            <DashboardLayout>
                <div className="flex h-full items-center justify-center p-8">
                    <p className="text-slate-400">Loading admin data...</p>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-7xl mx-auto">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-2">
                            <Shield className="h-8 w-8 text-indigo-500" />
                            Admin Console
                        </h1>
                        <p className="text-slate-400 mt-1">
                            Manage users, groups, permissions, and platform settings.
                        </p>
                    </div>
                </div>

                <Tabs defaultValue={defaultTab} className="space-y-6">
                    <TabsList className="bg-slate-950/40 border border-slate-800/50 rounded-xl p-1 backdrop-blur-sm h-auto flex-wrap gap-0.5">
                        <TabsTrigger value="users" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-indigo-500/10 data-[state=active]:text-indigo-400 data-[state=active]:shadow-[0_0_12px_rgba(99,102,241,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Users className="h-3.5 w-3.5" /> Operators
                        </TabsTrigger>
                        <TabsTrigger value="permissions" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-primary/10 data-[state=active]:text-primary data-[state=active]:shadow-[0_0_12px_rgba(168,85,247,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Shield className="h-3.5 w-3.5" /> Permissions
                        </TabsTrigger>
                        <TabsTrigger value="registration-codes" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-amber-500/10 data-[state=active]:text-amber-400 data-[state=active]:shadow-[0_0_12px_rgba(245,158,11,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Ticket className="h-3.5 w-3.5" /> Invite Codes
                        </TabsTrigger>
                        <TabsTrigger value="types" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400 data-[state=active]:shadow-[0_0_12px_rgba(6,182,212,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Layers className="h-3.5 w-3.5" /> Taxonomy
                        </TabsTrigger>
                        <TabsTrigger value="authentication" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-green-500/10 data-[state=active]:text-green-400 data-[state=active]:shadow-[0_0_12px_rgba(34,197,94,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Lock className="h-3.5 w-3.5" /> Auth & Sessions
                        </TabsTrigger>
                        <TabsTrigger value="api-tokens" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-rose-500/10 data-[state=active]:text-rose-400 data-[state=active]:shadow-[0_0_12px_rgba(244,63,94,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <KeyRound className="h-3.5 w-3.5" /> API Tokens
                        </TabsTrigger>
                        <TabsTrigger value="wordlists" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-teal-500/10 data-[state=active]:text-teal-400 data-[state=active]:shadow-[0_0_12px_rgba(20,184,166,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <BookOpen className="h-3.5 w-3.5" /> Wordlists
                        </TabsTrigger>
                        <TabsTrigger value="ai" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-violet-500/10 data-[state=active]:text-violet-400 data-[state=active]:shadow-[0_0_12px_rgba(139,92,246,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Brain className="h-3.5 w-3.5" /> AI Assistant
                        </TabsTrigger>
                        <TabsTrigger value="skills" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-pink-500/10 data-[state=active]:text-pink-400 data-[state=active]:shadow-[0_0_12px_rgba(236,72,153,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Radar className="h-3.5 w-3.5" /> Skills
                        </TabsTrigger>
                        <TabsTrigger value="widgets" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-fuchsia-500/10 data-[state=active]:text-fuchsia-400 data-[state=active]:shadow-[0_0_12px_rgba(217,70,239,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <LayoutGrid className="h-3.5 w-3.5" /> Widgets
                        </TabsTrigger>
                        <TabsTrigger value="plugins" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 data-[state=active]:shadow-[0_0_12px_rgba(16,185,129,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Plug className="h-3.5 w-3.5" /> Plugins
                        </TabsTrigger>
                        <TabsTrigger value="email" className="rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 data-[state=active]:bg-blue-500/10 data-[state=active]:text-blue-400 data-[state=active]:shadow-[0_0_12px_rgba(59,130,246,0.15)] hover:bg-slate-800/60 hover:text-slate-200 gap-1.5">
                            <Mail className="h-3.5 w-3.5" /> Email
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="users" className="space-y-6">
                        <div className="grid gap-4 md:grid-cols-3">
                            <Card className="border-slate-800 bg-slate-900/50">
                                <CardHeader className="flex flex-row items-center justify-between pb-2">
                                    <CardTitle className="text-sm font-medium text-slate-300">Total Users</CardTitle>
                                    <Users className="h-4 w-4 text-blue-400" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold text-white">{users?.length || 0}</div>
                                </CardContent>
                            </Card>
                            <Card className="border-slate-800 bg-slate-900/50">
                                <CardHeader className="flex flex-row items-center justify-between pb-2">
                                    <CardTitle className="text-sm font-medium text-slate-300">Operators Online</CardTitle>
                                    <CheckCircle2 className="h-4 w-4 text-green-400" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold text-white">
                                        {users?.filter(u => u.last_active && new Date(u.last_active).getTime() > Date.now() - 5 * 60 * 1000).length || 0}
                                    </div>
                                </CardContent>
                            </Card>
                            <Card className="border-slate-800 bg-slate-900/50">
                                <CardHeader className="flex flex-row items-center justify-between pb-2">
                                    <CardTitle className="text-sm font-medium text-slate-300">Admins</CardTitle>
                                    <Shield className="h-4 w-4 text-primary" />
                                </CardHeader>
                                <CardContent>
                                    <div className="text-2xl font-bold text-white">
                                        {users?.filter(u => u.role === UserRole.ADMIN || u.role === 'read_only_admin' as any).length || 0}
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        <Card className="border-slate-800 bg-slate-900/50">
                            <CardHeader>
                                <div className="flex items-center justify-between">
                                    <div>
                                        <CardTitle className="text-white">User Management</CardTitle>
                                        <CardDescription>Manage user access and global permissions</CardDescription>
                                    </div>
                                    <Button
                                        onClick={() => setIsCreateDialogOpen(true)}
                                        className="bg-primary hover:bg-primary/90 gap-2"
                                        size="sm"
                                    >
                                        <Plus className="h-4 w-4" />
                                        Add User
                                    </Button>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <Table>
                                    <TableHeader>
                                        <TableRow className="border-slate-800 hover:bg-slate-900/50">
                                            <TableHead className="text-slate-400">User</TableHead>
                                            <TableHead className="text-slate-400">Groups</TableHead>
                                            <TableHead className="text-slate-400">Permissions</TableHead>
                                            <TableHead className="text-slate-400">Status</TableHead>
                                            <TableHead className="text-slate-400">Created</TableHead>
                                            <TableHead className="text-slate-400 text-right">Actions</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {users?.map((user) => (
                                            <TableRow key={user.id} className="border-slate-800 hover:bg-slate-800/50">
                                                <TableCell>
                                                    <div className="flex items-center gap-3">
                                                        <div className="relative">
                                                            <UserAvatar
                                                                user={user}
                                                                className="h-10 w-10"
                                                            />
                                                            {user.last_active && new Date(user.last_active).getTime() > Date.now() - 5 * 60 * 1000 && (
                                                                <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-green-500 rounded-full border-2 border-slate-900" title="Active now" />
                                                            )}
                                                        </div>
                                                        <div className="flex flex-col">
                                                            <span className="font-medium text-white">{user.username}</span>
                                                            <span className="text-xs text-slate-500">{user.email}</span>
                                                        </div>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex flex-wrap gap-1 max-w-[200px]">
                                                        {(user as any).groups?.map((g: any) => (
                                                            <Badge key={g.id} variant="secondary" className="text-[10px] bg-indigo-500/10 text-indigo-400 border-indigo-500/20">
                                                                {g.name}
                                                            </Badge>
                                                        ))}
                                                        {(!(user as any).groups || (user as any).groups.length === 0) && (
                                                            <span className="text-xs text-slate-600 italic text-[10px]">No groups</span>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    {user.role === UserRole.ADMIN ? (
                                                        <Badge className="text-[10px] bg-purple-500/10 text-purple-400 border-purple-500/20">
                                                            Admin
                                                        </Badge>
                                                    ) : (user.role as string) === 'read_only_admin' ? (
                                                        <Badge className="text-[10px] bg-blue-500/10 text-blue-400 border-blue-500/20">
                                                            RO Admin
                                                        </Badge>
                                                    ) : (
                                                        <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-400">
                                                            User
                                                        </Badge>
                                                    )}
                                                </TableCell>
                                                <TableCell>
                                                    {(() => {
                                                        const lastActive = user.last_active ? new Date(user.last_active) : null;
                                                        const minutesAgo = lastActive ? (Date.now() - lastActive.getTime()) / (1000 * 60) : null;
                                                        const isOnline = minutesAgo !== null && minutesAgo < 5;
                                                        const isAway = minutesAgo !== null && minutesAgo >= 5 && minutesAgo < sessionTimeoutMinutes;
                                                        return (
                                                            <div className="flex flex-col gap-1.5">
                                                                <div className="flex items-center gap-1.5">
                                                                    {isOnline ? (
                                                                        <Badge className="bg-green-500/10 text-green-400 border-green-500/20 gap-1 py-0.5 text-[10px]">
                                                                            <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
                                                                            ONLINE
                                                                        </Badge>
                                                                    ) : isAway ? (
                                                                        <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1 py-0.5 text-[10px]">
                                                                            <div className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                                                                            AWAY
                                                                        </Badge>
                                                                    ) : (
                                                                        <Badge variant="outline" className="text-slate-500 border-slate-700 gap-1 py-0.5 text-[10px]">
                                                                            <Clock className="h-2.5 w-2.5" />
                                                                            OFFLINE
                                                                        </Badge>
                                                                    )}
                                                                    <Badge
                                                                        variant={user.is_active ? "outline" : "destructive"}
                                                                        className={user.is_active
                                                                            ? "bg-green-500/10 text-green-400 border-green-500/20 py-0.5 text-[10px]"
                                                                            : "bg-red-500/10 text-red-400 border-red-500/20 py-0.5 text-[10px]"}
                                                                    >
                                                                        {user.is_active ? 'ENABLED' : 'DISABLED'}
                                                                    </Badge>
                                                                </div>
                                                                <span className="text-[10px] text-slate-500 italic ml-0.5">
                                                                    {isOnline && lastActive ? (
                                                                        <span className="flex items-center gap-1">
                                                                            <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
                                                                            {formatDistanceToNow(parseUTCDate(user.last_active!), { addSuffix: true })}
                                                                        </span>
                                                                    ) : lastActive ? (
                                                                        formatDistanceToNow(parseUTCDate(user.last_active!), { addSuffix: true })
                                                                    ) : (
                                                                        'Logged out'
                                                                    )}
                                                                </span>
                                                            </div>
                                                        );
                                                    })()}
                                                </TableCell>
                                                <TableCell className="text-slate-400 text-sm whitespace-nowrap">
                                                    <div className="flex flex-col gap-0.5">
                                                        <span>{format(new Date(user.created_at), 'MMM d, yyyy')}</span>
                                                        <span className="text-[10px] text-slate-500 italic">
                                                            Login: {user.last_login ? format(new Date(user.last_login), 'HH:mm') : 'Never'}
                                                        </span>
                                                    </div>
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger asChild>
                                                            <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-slate-800 text-slate-400">
                                                                <MoreVertical className="h-4 w-4" />
                                                            </Button>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="end" className="bg-slate-950 border-slate-800">
                                                            <DropdownMenuLabel className="text-slate-400 text-xs">{user.username}</DropdownMenuLabel>
                                                            <DropdownMenuSeparator className="bg-slate-800" />
                                                            <DropdownMenuItem onClick={() => handleEditClick(user)} className="gap-2 cursor-pointer">
                                                                <Edit className="h-3.5 w-3.5 text-indigo-400" />
                                                                Edit Groups
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem onClick={() => handleResetPassword(user.id)} className="gap-2 cursor-pointer">
                                                                <Key className="h-3.5 w-3.5 text-amber-400" />
                                                                Reset Password
                                                            </DropdownMenuItem>
                                                            <DropdownMenuSeparator className="bg-slate-800" />
                                                            <DropdownMenuItem
                                                                onClick={() => handleStatusToggle(user)}
                                                                disabled={user.id === currentUser?.id}
                                                                className="gap-2 cursor-pointer"
                                                            >
                                                                {user.is_active ? (
                                                                    <><UserMinus className="h-3.5 w-3.5 text-amber-400" /> Disable Account</>
                                                                ) : (
                                                                    <><UserCheck className="h-3.5 w-3.5 text-green-400" /> Enable Account</>
                                                                )}
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem
                                                                onClick={() => handleDelete(user.id)}
                                                                disabled={user.id === currentUser?.id}
                                                                className="gap-2 cursor-pointer text-red-400 focus:text-red-300"
                                                            >
                                                                <Trash2 className="h-3.5 w-3.5" />
                                                                Delete User
                                                            </DropdownMenuItem>
                                                        </DropdownMenuContent>
                                                    </DropdownMenu>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    <TabsContent value="permissions" className="space-y-6">
                        <StatsScopeSettings />
                        <PermissionsManagement />
                    </TabsContent>

                    <TabsContent value="registration-codes" className="space-y-6">
                        <RegistrationCodeManagement />
                    </TabsContent>

                    <TabsContent value="types" className="space-y-6">
                        <TypeManagement />
                    </TabsContent>

                    <TabsContent value="authentication" className="space-y-6">
                        <AuthSettingsManagement />
                    </TabsContent>

                    <TabsContent value="api-tokens" className="space-y-6">
                        <ApiTokenManagement />
                    </TabsContent>

                    <TabsContent value="wordlists" className="space-y-6">
                        <WordlistManagement />
                    </TabsContent>

                    <TabsContent value="ai" className="space-y-6">
                        <AiSettingsManagement />
                    </TabsContent>

                    <TabsContent value="skills" className="space-y-6">
                        <SkillsAdminPanel />
                    </TabsContent>

                    <TabsContent value="widgets" className="space-y-6">
                        <WidgetManagement />
                    </TabsContent>

                    <TabsContent value="plugins" className="space-y-6">
                        <PluginManagement />
                    </TabsContent>

                    <TabsContent value="email" className="space-y-6">
                        <EmailSettings />
                    </TabsContent>
                </Tabs>

                {/* Edit User Dialog */}
                <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
                    <DialogContent className="bg-slate-950 border-slate-800 sm:max-w-[425px]">
                        <DialogHeader>
                            <DialogTitle className="text-white flex items-center gap-2">
                                <Settings className="h-5 w-5 text-indigo-400" />
                                Edit User: {selectedUser?.username}
                            </DialogTitle>
                            <DialogDescription className="text-slate-400">
                                Manage admin access and permission groups.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-6 py-4">
                            <div className="space-y-2 p-3 rounded-lg border border-slate-800 bg-slate-900/30">
                                <div className="flex items-center justify-between">
                                    <div className="space-y-1">
                                        <Label className="text-slate-300 flex items-center gap-2">
                                            <Shield className="h-4 w-4 text-primary" />
                                            Platform Admin
                                        </Label>
                                        <p className="text-[11px] text-slate-500">Full access to admin console and all platform settings.</p>
                                    </div>
                                    <Switch
                                        checked={editForm.isAdmin}
                                        onCheckedChange={(checked) => setEditForm({ ...editForm, isAdmin: checked, isReadOnlyAdmin: checked ? editForm.isReadOnlyAdmin : false })}
                                        disabled={selectedUser?.id === currentUser?.id}
                                    />
                                </div>
                                {editForm.isAdmin && (
                                    <div className="flex items-center gap-3 pt-2 border-t border-slate-800/60">
                                        <Checkbox
                                            id="edit-read-only-admin"
                                            checked={editForm.isReadOnlyAdmin}
                                            onCheckedChange={(checked) => setEditForm({ ...editForm, isReadOnlyAdmin: !!checked })}
                                            disabled={selectedUser?.id === currentUser?.id}
                                            className="border-slate-700 data-[state=checked]:bg-primary"
                                        />
                                        <div className="space-y-0.5">
                                            <Label htmlFor="edit-read-only-admin" className="text-slate-300 cursor-pointer text-sm">
                                                Read-only
                                            </Label>
                                            <p className="text-[11px] text-slate-500">Can view everything an admin can, but cannot modify data.</p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="space-y-3">
                                <Label className="text-slate-300">Groups</Label>
                                <p className="text-[11px] text-slate-500">Groups control feature permissions across the platform. Manage group permissions in the Permissions tab.</p>
                                <div className="grid grid-cols-1 gap-1 p-3 rounded-lg border border-slate-800 bg-slate-900/30 max-h-[220px] overflow-y-auto">
                                    {groups?.filter(g => g.name !== 'Administrators').map((group) => (
                                        <div key={group.id} className="flex items-center gap-3 py-1.5 px-1 rounded hover:bg-slate-800/40 transition-colors">
                                            <Checkbox
                                                id={`group-${group.id}`}
                                                checked={editForm.groupIds.includes(group.id)}
                                                onCheckedChange={(checked) => {
                                                    const newGroups = checked
                                                        ? [...editForm.groupIds, group.id]
                                                        : editForm.groupIds.filter(id => id !== group.id);
                                                    setEditForm({ ...editForm, groupIds: newGroups });
                                                }}
                                                className="border-slate-700 data-[state=checked]:bg-primary"
                                            />
                                            <div className="flex flex-col">
                                                <Label
                                                    htmlFor={`group-${group.id}`}
                                                    className="text-sm text-slate-300 cursor-pointer flex items-center gap-2"
                                                >
                                                    {group.name}
                                                    {group.is_default && (
                                                        <Badge variant="outline" className="text-[9px] py-0 px-1 border-indigo-500/30 text-indigo-400">Default</Badge>
                                                    )}
                                                    {group.is_system && (
                                                        <Badge variant="outline" className="text-[9px] py-0 px-1 border-amber-500/30 text-amber-400">System</Badge>
                                                    )}
                                                </Label>
                                                {group.description && (
                                                    <span className="text-[10px] text-slate-500">{group.description}</span>
                                                )}
                                                <span className="text-[10px] text-slate-600">
                                                    {group.permissions?.length || 0} permission{(group.permissions?.length || 0) !== 1 ? 's' : ''}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                    {(!groups || groups.length === 0) && (
                                        <p className="text-xs text-slate-500 italic">No groups defined. Create groups in the Permissions tab.</p>
                                    )}
                                </div>
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 mt-4">
                            <Button variant="ghost" onClick={() => setIsEditDialogOpen(false)}>Cancel</Button>
                            <Button onClick={handleUpdateUser} className="bg-primary hover:bg-primary/90">Save Changes</Button>
                        </div>
                    </DialogContent>
                </Dialog>

                {/* Password Reset Success Dialog */}
                <Dialog open={isPasswordDialogOpen} onOpenChange={setIsPasswordDialogOpen}>
                    <DialogContent className="bg-slate-950 border-slate-800 sm:max-w-[400px]">
                        <DialogHeader>
                            <DialogTitle className="text-white flex items-center gap-2">
                                <Key className="h-5 w-5 text-amber-400" />
                                Temporary Password Generated
                            </DialogTitle>
                            <DialogDescription className="text-slate-200">
                                Please copy this temporary password and provide it to the user.
                                They will need to log in with this password and should change it immediately.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="py-6">
                            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl flex items-center justify-between group">
                                <code className="text-xl font-mono text-amber-400 select-all">
                                    {tempPassword}
                                </code>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => {
                                        if (tempPassword) {
                                            navigator.clipboard.writeText(tempPassword);
                                            toast.success('Copied to clipboard');
                                        }
                                    }}
                                >
                                    <Check className="h-4 w-4 text-slate-400 group-hover:text-white" />
                                </Button>
                            </div>
                        </div>
                        <div className="flex justify-end">
                            <Button className="bg-amber-600 hover:bg-amber-500 text-white" onClick={() => setIsPasswordDialogOpen(false)}>
                                Done
                            </Button>
                        </div>
                    </DialogContent>
                </Dialog>

                <ConfirmDialog />

                {/* Create User Dialog */}
                <Dialog open={isCreateDialogOpen} onOpenChange={(open) => { setIsCreateDialogOpen(open); setCreateFormError(null); }}>
                    <DialogContent className="bg-slate-950 border-slate-800 sm:max-w-[440px]">
                        <DialogHeader>
                            <DialogTitle className="text-white flex items-center gap-2">
                                <Users className="h-5 w-5 text-indigo-400" />
                                Create Local User
                            </DialogTitle>
                            <DialogDescription className="text-slate-400">
                                Create a new local account. The user can log in immediately with these credentials.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-2">
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-1.5">
                                    <Label className="text-slate-300 text-xs">Username <span className="text-red-400">*</span></Label>
                                    <Input
                                        id="create-username"
                                        placeholder="jsmith"
                                        value={createForm.username}
                                        onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
                                        className="bg-slate-900 border-slate-700 text-white"
                                        autoComplete="off"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <Label className="text-slate-300 text-xs">Full Name</Label>
                                    <Input
                                        id="create-fullname"
                                        placeholder="John Smith"
                                        value={createForm.full_name}
                                        onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
                                        className="bg-slate-900 border-slate-700 text-white"
                                    />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Email <span className="text-red-400">*</span></Label>
                                <Input
                                    id="create-email"
                                    type="email"
                                    placeholder="jsmith@company.com"
                                    value={createForm.email}
                                    onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                                    className="bg-slate-900 border-slate-700 text-white"
                                    autoComplete="off"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Password <span className="text-red-400">*</span></Label>
                                <Input
                                    id="create-password"
                                    type="password"
                                    placeholder="Minimum 8 characters"
                                    value={createForm.password}
                                    onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                                    className="bg-slate-900 border-slate-700 text-white"
                                    autoComplete="new-password"
                                    onKeyDown={(e) => e.key === 'Enter' && handleCreateUser()}
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Role</Label>
                                <Select
                                    value={createForm.role}
                                    onValueChange={(val) => setCreateForm({ ...createForm, role: val })}
                                >
                                    <SelectTrigger className="bg-slate-900 border-slate-700 text-white">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-950 border-slate-800">
                                        <SelectItem value={UserRole.OPERATOR} className="text-slate-300">Operator</SelectItem>
                                        <SelectItem value={UserRole.READ_ONLY_ADMIN} className="text-slate-300">Read-Only Admin</SelectItem>
                                        <SelectItem value={UserRole.ADMIN} className="text-slate-300">Admin</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            {createFormError && (
                                <p className="text-sm text-red-400 flex items-center gap-1.5">
                                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                    {createFormError}
                                </p>
                            )}
                        </div>
                        <div className="flex justify-end gap-3 mt-2">
                            <Button variant="ghost" onClick={() => { setIsCreateDialogOpen(false); setCreateFormError(null); }}>
                                Cancel
                            </Button>
                            <Button
                                onClick={handleCreateUser}
                                disabled={createUser.isPending}
                                className="bg-primary hover:bg-primary/90 gap-2"
                            >
                                {createUser.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                                Create User
                            </Button>
                        </div>
                    </DialogContent>
                </Dialog>
            </div>
        </DashboardLayout>
    );
}


// ═══════════════════════════════════════════════════════════════════
//  SKILLS ADMIN PANEL
// ═══════════════════════════════════════════════════════════════════

function SkillsAdminPanel() {
    const { data: categories = [], isLoading } = useSkillCategories();
    const createCategory = useCreateSkillCategory();
    const updateCategory = useUpdateSkillCategory();
    const deleteCategory = useDeleteSkillCategory();
    const createSkill = useCreateSkill();
    const updateSkill = useUpdateSkill();
    const deleteSkill = useDeleteSkill();
    const seedSkills = useSeedSkills();

    const [newCatName, setNewCatName] = useState('');
    const [newCatColor, setNewCatColor] = useState('#6366f1');
    const [newSkillName, setNewSkillName] = useState('');
    const [newSkillCatId, setNewSkillCatId] = useState('');
    const [editingCat, setEditingCat] = useState<string | null>(null);
    const [editCatName, setEditCatName] = useState('');
    const [editCatColor, setEditCatColor] = useState('');

    const handleAddCategory = async () => {
        if (!newCatName.trim()) return;
        try {
            await createCategory.mutateAsync({ name: newCatName.trim(), color: newCatColor });
            setNewCatName('');
            toast.success('Category created');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to create category'));
        }
    };

    const handleUpdateCategory = async (catId: string) => {
        try {
            await updateCategory.mutateAsync({ id: catId, name: editCatName, color: editCatColor });
            setEditingCat(null);
            toast.success('Category updated');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to update category'));
        }
    };

    const handleDeleteCategory = async (catId: string) => {
        try {
            await deleteCategory.mutateAsync(catId);
            toast.success('Category deleted');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to delete category'));
        }
    };

    const handleAddSkill = async (categoryId: string) => {
        if (!newSkillName.trim()) return;
        try {
            await createSkill.mutateAsync({ category_id: categoryId, name: newSkillName.trim() });
            setNewSkillName('');
            setNewSkillCatId('');
            toast.success('Skill created');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to create skill'));
        }
    };

    const handleDeleteSkill = async (skillId: string) => {
        try {
            await deleteSkill.mutateAsync(skillId);
            toast.success('Skill deleted');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to delete skill'));
        }
    };

    const handleSeed = async () => {
        try {
            await seedSkills.mutateAsync();
            toast.success('Default skills seeded successfully!');
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to seed skills'));
        }
    };

    if (isLoading) {
        return (
            <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-pink-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                        <Radar className="h-5 w-5 text-pink-400" />
                        Skills Configuration
                    </h2>
                    <p className="text-sm text-slate-400 mt-1">
                        Configure skill categories and individual skills that operators can add to their profiles.
                    </p>
                </div>
                {categories.length === 0 && (
                    <Button
                        onClick={handleSeed}
                        disabled={seedSkills.isPending}
                        className="bg-pink-600 hover:bg-pink-700 text-white gap-2"
                    >
                        {seedSkills.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
                        Seed Default Skills
                    </Button>
                )}
            </div>

            {/* Add Category */}
            <Card className="border-slate-800 bg-slate-900/50">
                <CardContent className="pt-4">
                    <div className="flex items-center gap-3">
                        <Input
                            placeholder="New category name..."
                            value={newCatName}
                            onChange={(e) => setNewCatName(e.target.value)}
                            className="bg-slate-800 border-slate-700 text-white flex-1"
                            onKeyDown={(e) => e.key === 'Enter' && handleAddCategory()}
                        />
                        <input
                            type="color"
                            value={newCatColor}
                            onChange={(e) => setNewCatColor(e.target.value)}
                            className="w-9 h-9 rounded-md border border-slate-700 bg-transparent cursor-pointer"
                        />
                        <Button
                            onClick={handleAddCategory}
                            disabled={!newCatName.trim() || createCategory.isPending}
                            className="bg-pink-600 hover:bg-pink-700 gap-1"
                            size="sm"
                        >
                            <Plus className="h-4 w-4" />
                            Add Category
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Categories */}
            {categories.map((cat) => (
                <Card key={cat.id} className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            {editingCat === cat.id ? (
                                <div className="flex items-center gap-2 flex-1">
                                    <input
                                        type="color"
                                        value={editCatColor}
                                        onChange={(e) => setEditCatColor(e.target.value)}
                                        className="w-8 h-8 rounded border border-slate-700 bg-transparent cursor-pointer"
                                    />
                                    <Input
                                        value={editCatName}
                                        onChange={(e) => setEditCatName(e.target.value)}
                                        className="bg-slate-800 border-slate-700 text-white flex-1 h-8"
                                        onKeyDown={(e) => e.key === 'Enter' && handleUpdateCategory(cat.id)}
                                    />
                                    <Button size="sm" variant="ghost" onClick={() => handleUpdateCategory(cat.id)} className="text-green-400 h-8">
                                        <Check className="h-4 w-4" />
                                    </Button>
                                    <Button size="sm" variant="ghost" onClick={() => setEditingCat(null)} className="text-slate-400 h-8">
                                        <XCircle className="h-4 w-4" />
                                    </Button>
                                </div>
                            ) : (
                                <>
                                    <CardTitle className="text-white text-base flex items-center gap-2">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: cat.color || '#6366f1' }} />
                                        {cat.name}
                                        <Badge variant="outline" className="text-[10px] text-slate-500 border-slate-700">
                                            {cat.skills.length} skills
                                        </Badge>
                                    </CardTitle>
                                    <div className="flex items-center gap-1">
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => { setEditingCat(cat.id); setEditCatName(cat.name); setEditCatColor(cat.color || '#6366f1'); }}
                                            className="text-slate-500 hover:text-white h-7"
                                        >
                                            <Edit className="h-3.5 w-3.5" />
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => handleDeleteCategory(cat.id)}
                                            className="text-slate-500 hover:text-red-400 h-7"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </Button>
                                    </div>
                                </>
                            )}
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-1">
                        {cat.skills.map((skill) => (
                            <div
                                key={skill.id}
                                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-slate-800/40 transition-colors group"
                            >
                                <span className="text-sm text-white">{skill.name}</span>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => handleDeleteSkill(skill.id)}
                                    className="text-slate-600 hover:text-red-400 h-6 opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                    <Trash2 className="h-3 w-3" />
                                </Button>
                            </div>
                        ))}

                        {/* Add skill inline */}
                        {newSkillCatId === cat.id ? (
                            <div className="flex items-center gap-2 pt-2">
                                <Input
                                    placeholder="New skill name..."
                                    value={newSkillName}
                                    onChange={(e) => setNewSkillName(e.target.value)}
                                    className="bg-slate-800 border-slate-700 text-white h-8 text-sm flex-1"
                                    autoFocus
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') handleAddSkill(cat.id);
                                        if (e.key === 'Escape') { setNewSkillCatId(''); setNewSkillName(''); }
                                    }}
                                />
                                <Button size="sm" className="bg-pink-600 hover:bg-pink-700 h-8" onClick={() => handleAddSkill(cat.id)}>
                                    Add
                                </Button>
                                <Button size="sm" variant="ghost" className="h-8 text-slate-400" onClick={() => { setNewSkillCatId(''); setNewSkillName(''); }}>
                                    Cancel
                                </Button>
                            </div>
                        ) : (
                            <button
                                onClick={() => setNewSkillCatId(cat.id)}
                                className="w-full flex items-center gap-2 py-2 px-3 rounded-lg text-sm text-slate-600 hover:text-pink-400 hover:bg-slate-800/40 transition-colors"
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Add Skill
                            </button>
                        )}
                    </CardContent>
                </Card>
            ))}

            {categories.length === 0 && (
                <Card className="border-slate-800 bg-slate-900/50 border-dashed">
                    <CardContent className="py-12 text-center">
                        <Radar className="h-12 w-12 text-slate-700 mx-auto mb-3" />
                        <p className="text-slate-400">No skill categories configured.</p>
                        <p className="text-xs text-slate-600 mt-1">Use "Seed Default Skills" to get started quickly, or add categories manually above.</p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
