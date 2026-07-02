/**
 * admin/users/page.tsx — User Management (Legacy)
 *
 * Standalone user-management page with a table of all registered users.
 * Supports creating new users (username, email, password, role), editing
 * existing user details (name, role), and toggling active/suspended state.
 * Columns: user info, role badge, online/offline status with last-active
 * distance, and a dropdown action menu. This page predates the unified
 * Admin Console and is retained for backward-compatible deep links.
 */
'use client';

import { useState } from 'react';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem,
    DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import {
    Dialog, DialogContent, DialogDescription, DialogFooter,
    DialogHeader, DialogTitle, DialogTrigger
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { toast } from 'sonner';
import {
    Users, UserPlus, MoreVertical, Edit, Shield, Mail,
    Clock, CheckCircle, XCircle, Loader2, ArrowLeft, Key, Activity
} from 'lucide-react';
import { useUsers, useUpdateUser, useCreateUser } from '@/lib/hooks/use-users';
import api, { apiErrorMessage } from '@/lib/api';
import { UserRole } from '@/lib/types';
import { format, formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { useRouter } from 'next/navigation';

export default function AdminUsersPage() {
    const router = useRouter();
    const { data: users = [], isLoading } = useUsers();
    const updateUser = useUpdateUser();
    const createUser = useCreateUser();

    const [selectedUser, setSelectedUser] = useState<any>(null);
    const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
    const [isAddUserOpen, setIsAddUserOpen] = useState(false);

    const [newUser, setNewUser] = useState({
        username: '',
        email: '',
        password: '',
        full_name: '',
        role: 'operator'
    });

    const handleCreateUser = async () => {
        try {
            await createUser.mutateAsync(newUser);
            setIsAddUserOpen(false);
            setNewUser({
                username: '',
                email: '',
                password: '',
                full_name: '',
                role: 'operator'
            });
        } catch (err: any) {
            console.error('Failed to create user:', err);
            toast.error(apiErrorMessage(err, 'Failed to create user'));
        }
    };

    const handleToggleActive = async (user: any) => {
        try {
            await updateUser.mutateAsync({ id: user.id, is_active: !user.is_active });
        } catch (error) {
            console.error('Failed to update user status:', error);
            toast.error('Failed to update user status');
        }
    };

    const getUserRoleBadge = (role: string) => {
        const roles: Record<string, any> = {
            admin: { label: 'Admin', variant: 'destructive' },
            read_only_admin: { label: 'RO Admin', variant: 'default' },
            team_lead: { label: 'Team Lead', variant: 'default' },
            operator: { label: 'Operator', variant: 'secondary' },
            read_only: { label: 'Read Only', variant: 'outline' },
        };
        const r = roles[role] || roles.operator;
        return <Badge variant={r.variant}>{r.label}</Badge>;
    };

    if (isLoading) {
        return (
            <DashboardLayout>
                <div className="flex h-[60vh] items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-7xl mx-auto">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Button variant="ghost" size="icon" onClick={() => router.push('/dashboard')} className="text-slate-400">
                            <ArrowLeft className="h-5 w-5" />
                        </Button>
                        <div>
                            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                                <Shield className="h-8 w-8 text-primary" />
                                User Management
                            </h1>
                            <p className="text-slate-400 mt-1">Manage system access, roles, and status</p>
                        </div>
                    </div>
                    <Button
                        onClick={() => setIsAddUserOpen(true)}
                        className="bg-primary hover:bg-primary/90"
                    >
                        <UserPlus className="h-4 w-4 mr-2" /> Add New User
                    </Button>
                </div>

                <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md">
                    <CardHeader>
                        <CardTitle className="text-white">System Users</CardTitle>
                        <CardDescription>A list of all users registered in the platform</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow className="border-slate-800 hover:bg-transparent">
                                    <TableHead className="text-slate-400">User</TableHead>
                                    <TableHead className="text-slate-400">Role</TableHead>
                                    <TableHead className="text-slate-400">Status</TableHead>
                                    <TableHead className="text-slate-400">Last Login</TableHead>
                                    <TableHead className="text-right text-slate-400">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {users.map((user) => (
                                    <TableRow key={user.id} className="border-slate-800 hover:bg-slate-800/30">
                                        <TableCell>
                                            <div className="flex flex-col">
                                                <span className="font-bold text-white">{user.full_name || user.username}</span>
                                                <span className="text-xs text-slate-500 flex items-center gap-1">
                                                    <Mail className="h-3 w-3" /> {user.email}
                                                </span>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            {getUserRoleBadge(user.role)}
                                        </TableCell>
                                        <TableCell>
                                            {(() => {
                                                const isActive = user.is_active;
                                                const lastActive = user.last_active ? new Date(user.last_active) : null;
                                                const isOnline = lastActive && (new Date().getTime() - lastActive.getTime()) < 5 * 60 * 1000;

                                                if (!isActive) {
                                                    return (
                                                        <Badge variant="outline" className="text-slate-500 border-slate-700 gap-1.5 py-0.5">
                                                            <XCircle className="h-3 w-3" /> Suspended
                                                        </Badge>
                                                    );
                                                }

                                                if (isOnline) {
                                                    return (
                                                        <Badge className="bg-green-500/10 text-green-500 border-green-500/20 gap-1.5 py-0.5 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.2)]">
                                                            <div className="h-1.5 w-1.5 rounded-full bg-green-500 shadow-[0_0_4px_rgba(34,197,94,0.8)]" />
                                                            Online
                                                        </Badge>
                                                    );
                                                }

                                                return (
                                                    <Badge variant="outline" className="text-slate-400 border-slate-800 gap-1.5 py-0.5">
                                                        <Clock className="h-3 w-3" /> Offline
                                                    </Badge>
                                                );
                                            })()}
                                        </TableCell>
                                        <TableCell className="text-slate-400 text-sm">
                                            <div className="flex flex-col gap-0.5">
                                                <div className="flex items-center gap-2">
                                                    <Activity className={`h-3 w-3 ${user.last_active ? 'text-blue-400' : 'text-slate-600'}`} />
                                                    <span className="text-xs uppercase font-semibold text-slate-500">Activity: </span>
                                                    {user.last_active ? formatDistanceToNow(parseUTCDate(user.last_active), { addSuffix: true }) : 'Never'}
                                                </div>
                                                <div className="flex items-center gap-2 text-[10px] text-slate-500 ml-5 italic">
                                                    Login: {user.last_login ? format(new Date(user.last_login), 'MMM d, HH:mm') : 'Never'}
                                                </div>
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" size="icon" className="text-slate-400 hover:text-white">
                                                        <MoreVertical className="h-4 w-4" />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end" className="bg-slate-900 border-slate-800 text-white">
                                                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                    <DropdownMenuSeparator className="bg-slate-800" />
                                                    <DropdownMenuItem onClick={() => { setSelectedUser(user); setIsEditDialogOpen(true); }} className="hover:bg-slate-800">
                                                        <Edit className="h-4 w-4 mr-2" /> Edit User
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem onClick={() => handleToggleActive(user)} className="hover:bg-slate-800">
                                                        {user.is_active ? <XCircle className="h-4 w-4 mr-2 text-red-400" /> : <CheckCircle className="h-4 w-4 mr-2 text-green-400" />}
                                                        {user.is_active ? 'Deactivate' : 'Activate'}
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
            </div>

            {/* Edit User Dialog */}
            <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white">
                    <DialogHeader>
                        <DialogTitle>Edit User: {selectedUser?.username}</DialogTitle>
                        <DialogDescription className="text-slate-400">Modify user role and information.</DialogDescription>
                    </DialogHeader>
                    <div className="py-4 space-y-4">
                        <div className="space-y-2">
                            <Label>Full Name</Label>
                            <Input
                                value={selectedUser?.full_name || ''}
                                onChange={e => setSelectedUser({ ...selectedUser, full_name: e.target.value })}
                                className="bg-slate-800 border-slate-700"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Role</Label>
                            <Select
                                value={selectedUser?.role}
                                onValueChange={val => setSelectedUser({ ...selectedUser, role: val })}
                            >
                                <SelectTrigger className="bg-slate-800 border-slate-700 font-bold">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    <SelectItem value="admin">Admin</SelectItem>
                                    <SelectItem value="read_only_admin">Read-Only Admin</SelectItem>
                                    <SelectItem value="team_lead">Team Lead</SelectItem>
                                    <SelectItem value="operator">Operator</SelectItem>
                                    <SelectItem value="read_only">Read Only</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setIsEditDialogOpen(false)} className="border-slate-700 text-slate-400">Cancel</Button>
                        <Button
                            className="bg-primary hover:bg-primary/90"
                            disabled={updateUser.isPending}
                            onClick={async () => {
                                await updateUser.mutateAsync({
                                    id: selectedUser.id,
                                    full_name: selectedUser.full_name,
                                    role: selectedUser.role
                                });
                                setIsEditDialogOpen(false);
                            }}
                        >
                            {updateUser.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                            Save Changes
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Add User Dialog */}
            <Dialog open={isAddUserOpen} onOpenChange={setIsAddUserOpen}>
                <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-[425px]">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <UserPlus className="h-5 w-5 text-primary" />
                            Create New User
                        </DialogTitle>
                        <DialogDescription className="text-slate-400">Enter user details to create a new account.</DialogDescription>
                    </DialogHeader>
                    <div className="py-4 space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Username</Label>
                                <Input
                                    value={newUser.username}
                                    onChange={e => setNewUser({ ...newUser, username: e.target.value })}
                                    className="bg-slate-800 border-slate-700"
                                    placeholder="jdoe"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Full Name</Label>
                                <Input
                                    value={newUser.full_name}
                                    onChange={e => setNewUser({ ...newUser, full_name: e.target.value })}
                                    className="bg-slate-800 border-slate-700"
                                    placeholder="John Doe"
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Email</Label>
                            <Input
                                type="email"
                                value={newUser.email}
                                onChange={e => setNewUser({ ...newUser, email: e.target.value })}
                                className="bg-slate-800 border-slate-700"
                                placeholder="john@example.com"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Initial Password</Label>
                            <div className="relative">
                                <Input
                                    type="password"
                                    value={newUser.password}
                                    onChange={e => setNewUser({ ...newUser, password: e.target.value })}
                                    className="bg-slate-800 border-slate-700 pl-9"
                                    placeholder="••••••••"
                                />
                                <Key className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Role</Label>
                            <Select
                                value={newUser.role}
                                onValueChange={val => setNewUser({ ...newUser, role: val })}
                            >
                                <SelectTrigger className="bg-slate-800 border-slate-700 font-bold">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                    <SelectItem value="admin">Admin</SelectItem>
                                    <SelectItem value="read_only_admin">Read-Only Admin</SelectItem>
                                    <SelectItem value="team_lead">Team Lead</SelectItem>
                                    <SelectItem value="operator">Operator</SelectItem>
                                    <SelectItem value="read_only">Read Only</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setIsAddUserOpen(false)} className="border-slate-700 text-slate-400">Cancel</Button>
                        <Button
                            className="bg-primary hover:bg-primary/90"
                            disabled={createUser.isPending}
                            onClick={handleCreateUser}
                        >
                            {createUser.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                            Create User
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </DashboardLayout>
    );
}
