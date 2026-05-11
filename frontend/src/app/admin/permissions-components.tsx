// Permission dialog components for admin page
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Separator } from '@/components/ui/separator';
import { useGroups, useEngagementRoles, Group, EngagementRole, PermissionCategory } from '@/lib/hooks/use-admin-permissions';

// Group Permissions Dialog Component
export function GroupPermissionsDialog({
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
    const { data: groups } = useGroups();
    const liveGroup = groups?.find(g => g.id === group.id) || group;

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
                                            checked={liveGroup.permissions.includes(permission.value)}
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
export function RolePermissionsDialog({
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
    const { data: roles } = useEngagementRoles();
    const liveRole = roles?.find(r => r.id === role.id) || role;

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
                                            checked={liveRole.permissions.includes(permission.value)}
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
