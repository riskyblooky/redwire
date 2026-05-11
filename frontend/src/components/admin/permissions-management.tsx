'use client';

import { useState } from 'react';
import { usePermissionCategories as usePermissions, useGroups, useEngagementRoles, useCreateGroup, useUpdateGroup, useDeleteGroup, useUpdateGroupPermissions, useCreateEngagementRole, useUpdateEngagementRole, useDeleteEngagementRole, useUpdateEngagementRolePermissions, Group, EngagementRole, PermissionCategory } from '@/lib/hooks/use-admin-permissions';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Users, UserCog, Trash2, Edit, Plus, Lock } from 'lucide-react';
import { toast } from 'sonner';
import { Separator } from '@/components/ui/separator';

export function PermissionsManagement() {
    const [activeTab, setActiveTab] = useState('groups');
    const [editingGroup, setEditingGroup] = useState<Group | null>(null);
    const [editingRole, setEditingRole] = useState<EngagementRole | null>(null);
    const [createGroupOpen, setCreateGroupOpen] = useState(false);
    const [createRoleOpen, setCreateRoleOpen] = useState(false);

    const { data: permissionCategories, isLoading: permissionsLoading } = usePermissions();
    const { data: groups, isLoading: groupsLoading } = useGroups();
    const { data: roles, isLoading: rolesLoading } = useEngagementRoles();

    const createGroup = useCreateGroup();
    const updateGroup = useUpdateGroup();
    const deleteGroup = useDeleteGroup();
    const updateGroupPermissions = useUpdateGroupPermissions();

    const createRole = useCreateEngagementRole();
    const updateRole = useUpdateEngagementRole();
    const deleteRole = useDeleteEngagementRole();
    const updateRolePermissions = useUpdateEngagementRolePermissions();

    const handleCreateGroup = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);

        try {
            await createGroup.mutateAsync({
                name: formData.get('name') as string,
                description: formData.get('description') as string || undefined,
            });
            toast.success('Group created successfully');
            setCreateGroupOpen(false);
            (e.target as HTMLFormElement).reset();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to create group');
        }
    };

    const handleCreateRole = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);

        try {
            await createRole.mutateAsync({
                name: formData.get('name') as string,
                description: formData.get('description') as string || undefined,
            });
            toast.success('Role created successfully');
            setCreateRoleOpen(false);
            (e.target as HTMLFormElement).reset();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to create role');
        }
    };

    const handleDeleteGroup = async (groupId: string) => {
        try {
            await deleteGroup.mutateAsync(groupId);
            toast.success('Group deleted successfully');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delete group');
        }
    };

    const handleDeleteRole = async (roleId: string) => {
        try {
            await deleteRole.mutateAsync(roleId);
            toast.success('Role deleted successfully');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delete role');
        }
    };

    const handleToggleGroupPermission = async (group: Group, permissionValue: string) => {
        const currentPermissions = group.permissions || [];
        const newPermissions = currentPermissions.includes(permissionValue)
            ? currentPermissions.filter(p => p !== permissionValue)
            : [...currentPermissions, permissionValue];

        try {
            await updateGroupPermissions.mutateAsync({
                groupId: group.id,
                permissions: newPermissions,
            });
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to update permissions');
        }
    };

    const handleToggleRolePermission = async (role: EngagementRole, permissionValue: string) => {
        const currentPermissions = role.permissions || [];
        const newPermissions = currentPermissions.includes(permissionValue)
            ? currentPermissions.filter(p => p !== permissionValue)
            : [...currentPermissions, permissionValue];

        try {
            await updateRolePermissions.mutateAsync({
                roleId: role.id,
                permissions: newPermissions,
            });
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to update permissions');
        }
    };

    return (
        <div className="space-y-6">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
                <TabsList className="bg-slate-900/50 border border-slate-800">
                    <TabsTrigger value="groups" className="data-[state=active]:bg-slate-800">
                        <Users className="w-4 h-4 mr-2" />
                        Site-Wide Groups
                    </TabsTrigger>
                    <TabsTrigger value="roles" className="data-[state=active]:bg-slate-800">
                        <UserCog className="w-4 h-4 mr-2" />
                        Engagement Roles
                    </TabsTrigger>
                </TabsList>

                {/* Groups Tab */}
                <TabsContent value="groups" className="space-y-6">
                    <div className="flex justify-between items-center">
                        <h2 className="text-xl font-semibold text-white">Site-Wide Groups</h2>
                        <Dialog open={createGroupOpen} onOpenChange={setCreateGroupOpen}>
                            <DialogTrigger asChild>
                                <Button className="bg-primary hover:bg-primary/90">
                                    <Plus className="w-4 h-4 mr-2" />
                                    Create Group
                                </Button>
                            </DialogTrigger>
                            <DialogContent className="bg-slate-900 border-slate-800">
                                <DialogHeader>
                                    <DialogTitle>Create New Group</DialogTitle>
                                    <DialogDescription>Create a site-wide permission group</DialogDescription>
                                </DialogHeader>
                                <form onSubmit={handleCreateGroup} className="space-y-4">
                                    <div>
                                        <Label>Group Name</Label>
                                        <Input name="name" placeholder="e.g., Administrators" required />
                                    </div>
                                    <div>
                                        <Label>Description</Label>
                                        <Textarea name="description" placeholder="Describe this group's purpose..." />
                                    </div>
                                    <DialogFooter>
                                        <Button type="submit" disabled={createGroup.isPending}>
                                            {createGroup.isPending ? 'Creating...' : 'Create Group'}
                                        </Button>
                                    </DialogFooter>
                                </form>
                            </DialogContent>
                        </Dialog>
                    </div>

                    {groupsLoading && <p className="text-slate-400">Loading groups...</p>}

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {groups?.map((group) => (
                            <Card key={group.id} className="bg-slate-900/50 border-slate-800">
                                <CardHeader>
                                    <div className="flex justify-between items-start">
                                        <div>
                                            <CardTitle className="text-white flex items-center gap-2">
                                                {group.name}
                                                {(group.is_system || group.is_default) && (
                                                    <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400 gap-1">
                                                        <Lock className="w-3 h-3" />
                                                        {group.is_default ? 'Default' : 'System'}
                                                    </Badge>
                                                )}
                                            </CardTitle>
                                            <CardDescription className="text-slate-400">
                                                {group.description || 'No description'}
                                            </CardDescription>
                                            <Badge variant="outline" className="mt-2 border-slate-700 text-slate-300">
                                                {group.member_count || 0} members
                                            </Badge>
                                        </div>
                                        <div className="flex gap-2">
                                            <Button
                                                size="icon"
                                                variant="ghost"
                                                onClick={() => setEditingGroup(group)}
                                                className="text-slate-400 hover:text-white"
                                            >
                                                <Edit className="w-4 h-4" />
                                            </Button>
                                            {!group.is_system && !group.is_default && (
                                                <AlertDialog>
                                                    <AlertDialogTrigger asChild>
                                                        <Button
                                                            size="icon"
                                                            variant="ghost"
                                                            className="text-slate-400 hover:text-red-400"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </Button>
                                                    </AlertDialogTrigger>
                                                    <AlertDialogContent className="bg-slate-900 border-slate-800">
                                                        <AlertDialogHeader>
                                                            <AlertDialogTitle>Delete Group?</AlertDialogTitle>
                                                            <AlertDialogDescription>
                                                                Are you sure you want to delete {group.name}? This action cannot be undone.
                                                            </AlertDialogDescription>
                                                        </AlertDialogHeader>
                                                        <AlertDialogFooter>
                                                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                                                            <AlertDialogAction
                                                                onClick={() => handleDeleteGroup(group.id)}
                                                                className="bg-red-600 hover:bg-red-700"
                                                            >
                                                                Delete
                                                            </AlertDialogAction>
                                                        </AlertDialogFooter>
                                                    </AlertDialogContent>
                                                </AlertDialog>
                                            )}
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-sm text-slate-400 mb-2">
                                        {group.permissions?.length || 0} permissions granted
                                    </p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    {/* Edit Group Permissions Dialog */}
                    {editingGroup && (
                        <GroupPermissionsDialog
                            group={editingGroup}
                            categories={permissionCategories || []}
                            onToggle={handleToggleGroupPermission}
                            onClose={() => setEditingGroup(null)}
                        />
                    )}
                </TabsContent>

                {/* Engagement Roles Tab */}
                <TabsContent value="roles" className="space-y-6">
                    <div className="flex justify-between items-center">
                        <h2 className="text-xl font-semibold text-white">Engagement Roles</h2>
                        <Dialog open={createRoleOpen} onOpenChange={setCreateRoleOpen}>
                            <DialogTrigger asChild>
                                <Button className="bg-primary hover:bg-primary/90">
                                    <Plus className="w-4 h-4 mr-2" />
                                    Create Role
                                </Button>
                            </DialogTrigger>
                            <DialogContent className="bg-slate-900 border-slate-800">
                                <DialogHeader>
                                    <DialogTitle>Create New Role</DialogTitle>
                                    <DialogDescription>Create an engagement-specific role</DialogDescription>
                                </DialogHeader>
                                <form onSubmit={handleCreateRole} className="space-y-4">
                                    <div>
                                        <Label>Role Name</Label>
                                        <Input name="name" placeholder="e.g., Engagement Lead" required />
                                    </div>
                                    <div>
                                        <Label>Description</Label>
                                        <Textarea name="description" placeholder="Describe this role's purpose..." />
                                    </div>
                                    <DialogFooter>
                                        <Button type="submit" disabled={createRole.isPending}>
                                            {createRole.isPending ? 'Creating...' : 'Create Role'}
                                        </Button>
                                    </DialogFooter>
                                </form>
                            </DialogContent>
                        </Dialog>
                    </div>

                    {rolesLoading && <p className="text-slate-400">Loading roles...</p>}

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {roles?.map((role) => (
                            <Card key={role.id} className="bg-slate-900/50 border-slate-800">
                                <CardHeader>
                                    <div className="flex justify-between items-start">
                                        <div>
                                            <CardTitle className="text-white">{role.name}</CardTitle>
                                            <CardDescription className="text-slate-400">
                                                {role.description || 'No description'}
                                            </CardDescription>
                                        </div>
                                        <div className="flex gap-2">
                                            <Button
                                                size="icon"
                                                variant="ghost"
                                                onClick={() => setEditingRole(role)}
                                                className="text-slate-400 hover:text-white"
                                            >
                                                <Edit className="w-4 h-4" />
                                            </Button>
                                            <AlertDialog>
                                                <AlertDialogTrigger asChild>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        className="text-slate-400 hover:text-red-400"
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </Button>
                                                </AlertDialogTrigger>
                                                <AlertDialogContent className="bg-slate-900 border-slate-800">
                                                    <AlertDialogHeader>
                                                        <AlertDialogTitle>Delete Role?</AlertDialogTitle>
                                                        <AlertDialogDescription>
                                                            Are you sure you want to delete {role.name}? This action cannot be undone.
                                                        </AlertDialogDescription>
                                                    </AlertDialogHeader>
                                                    <AlertDialogFooter>
                                                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                                                        <AlertDialogAction
                                                            onClick={() => handleDeleteRole(role.id)}
                                                            className="bg-red-600 hover:bg-red-700"
                                                        >
                                                            Delete
                                                        </AlertDialogAction>
                                                    </AlertDialogFooter>
                                                </AlertDialogContent>
                                            </AlertDialog>
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-sm text-slate-400 mb-2">
                                        {role.permissions?.length || 0} permissions granted
                                    </p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    {/* Edit Role Permissions Dialog */}
                    {editingRole && (
                        <RolePermissionsDialog
                            role={editingRole}
                            categories={permissionCategories || []}
                            onToggle={handleToggleRolePermission}
                            onClose={() => setEditingRole(null)}
                        />
                    )}
                </TabsContent>
            </Tabs>
        </div>
    );
}

// Group Permissions Dialog Component
function GroupPermissionsDialog({
    group,
    categories,
    onToggle,
    onClose,
}: {
    group: Group;
    categories: PermissionCategory[];
    onToggle: (group: Group, permissionValue: string) => void;
    onClose: () => void;
}) {
    // Get live data from query to show real-time updates
    const { data: groups } = useGroups();
    const liveGroup = groups?.find(g => g.id === group.id) || group;

    // Filter to only global permissions
    const globalCategories = categories.map(cat => ({
        ...cat,
        permissions: cat.permissions.filter(p => p.is_global)
    })).filter(cat => cat.permissions.length > 0);

    return (
        <Dialog open={true} onOpenChange={onClose}>
            <DialogContent className="bg-slate-900 border-slate-800 max-w-3xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-white">Edit Permissions: {liveGroup.name}</DialogTitle>
                    <DialogDescription>Configure global site permissions for this group</DialogDescription>
                </DialogHeader>
                <div className="space-y-6">
                    {globalCategories.map((category) => (
                        <div key={category.category}>
                            <h3 className="font-semibold text-white mb-3">{category.category}</h3>
                            <div className="space-y-2 pl-4">
                                {category.permissions.map((permission) => (
                                    <div key={permission.value} className="flex items-center space-x-2">
                                        <Checkbox
                                            id={`group-${liveGroup.id}-${permission.value}`}
                                            checked={(liveGroup.permissions || []).includes(permission.value)}
                                            onCheckedChange={() => onToggle(liveGroup, permission.value)}
                                        />
                                        <Label
                                            htmlFor={`group-${liveGroup.id}-${permission.value}`}
                                            className="text-sm text-slate-300 cursor-pointer hover:text-white"
                                        >
                                            {permission.name}
                                        </Label>
                                    </div>
                                ))}
                            </div>
                            <Separator className="mt-4 bg-slate-800" />
                        </div>
                    ))}
                </div>
            </DialogContent>
        </Dialog>
    );
}

// Role Permissions Dialog Component
function RolePermissionsDialog({
    role,
    categories,
    onToggle,
    onClose,
}: {
    role: EngagementRole;
    categories: PermissionCategory[];
    onToggle: (role: EngagementRole, permissionValue: string) => void;
    onClose: () => void;
}) {
    // Get live data from query to show real-time updates
    const { data: roles } = useEngagementRoles();
    const liveRole = roles?.find(r => r.id === role.id) || role;

    // Filter to only engagement permissions
    const engagementCategories = categories.map(cat => ({
        ...cat,
        permissions: cat.permissions.filter(p => p.is_engagement)
    })).filter(cat => cat.permissions.length > 0);

    return (
        <Dialog open={true} onOpenChange={onClose}>
            <DialogContent className="bg-slate-900 border-slate-800 max-w-3xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-white">Edit Permissions: {liveRole.name}</DialogTitle>
                    <DialogDescription>Configure engagement-specific permissions for this role</DialogDescription>
                </DialogHeader>
                <div className="space-y-6">
                    {engagementCategories.map((category) => (
                        <div key={category.category}>
                            <h3 className="font-semibold text-white mb-3">{category.category}</h3>
                            <div className="space-y-2 pl-4">
                                {category.permissions.map((permission) => (
                                    <div key={permission.value} className="flex items-center space-x-2">
                                        <Checkbox
                                            id={`role-${liveRole.id}-${permission.value}`}
                                            checked={(liveRole.permissions || []).includes(permission.value)}
                                            onCheckedChange={() => onToggle(liveRole, permission.value)}
                                        />
                                        <Label
                                            htmlFor={`role-${liveRole.id}-${permission.value}`}
                                            className="text-sm text-slate-300 cursor-pointer hover:text-white"
                                        >
                                            {permission.name}
                                        </Label>
                                    </div>
                                ))}
                            </div>
                            <Separator className="mt-4 bg-slate-800" />
                        </div>
                    ))}
                </div>
            </DialogContent>
        </Dialog>
    );
}
