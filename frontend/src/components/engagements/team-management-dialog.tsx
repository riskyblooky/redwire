'use client';

import { useState, useEffect } from 'react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useUsers } from '@/lib/hooks/use-users';
import { useEngagementRoles } from '@/lib/hooks/use-rbac';
import { useUpdateEngagement, Engagement } from '@/lib/hooks/use-engagements';
import { UserPlus, Trash2, Shield, Loader2, User } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { UserAvatar } from '@/components/ui/user-avatar';

interface TeamManagementDialogProps {
    engagement: Engagement;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function TeamManagementDialog({ engagement, open, onOpenChange }: TeamManagementDialogProps) {
    const { data: users = [], isLoading: isLoadingUsers } = useUsers();
    const { data: roles = [], isLoading: isLoadingRoles } = useEngagementRoles();
    const updateEngagement = useUpdateEngagement();

    const [assignments, setAssignments] = useState<{ user_id: string; role_id: string }[]>([]);

    useEffect(() => {
        if (open && engagement.assignment_details) {
            setAssignments(
                engagement.assignment_details.map(a => ({
                    user_id: a.user_id,
                    role_id: a.role_id || '',
                }))
            );
        }
    }, [open, engagement]);

    const handleAddUser = () => {
        // Find first available user not already assigned
        const availableUser = users.find(u => !assignments.some(a => a.user_id === u.id));
        if (availableUser) {
            const defaultRole = roles.find(r => r.name === 'Pentester') || roles[0];
            setAssignments([...assignments, { user_id: availableUser.id, role_id: defaultRole?.id || '' }]);
        } else {
            toast.error("No more users available to assign");
        }
    };

    const handleRemoveUser = (userId: string) => {
        setAssignments(assignments.filter(a => a.user_id !== userId));
    };

    const handleUpdateAssignment = (userId: string, field: 'user_id' | 'role_id', value: string) => {
        setAssignments(assignments.map(a =>
            a.user_id === userId ? { ...a, [field]: value } : a
        ));
    };

    const handleSave = async () => {
        try {
            // Validate that all assignments have both user and role
            const validAssignments = assignments.filter(a => a.user_id && a.role_id);

            await updateEngagement.mutateAsync({
                id: engagement.id,
                assignments: validAssignments
            });

            toast.success("Team assignments updated successfully");
            onOpenChange(false);
        } catch (error) {
            console.error("Failed to update team:", error);
            toast.error("Failed to update team assignments");
        }
    };

    // Backend `/users` now filters to is_active=True at the query layer
    // (users.py::get_users), so the frontend can render the response
    // directly. Previously we filtered `u.is_active` here, but the
    // switch to UserSummary (which omits is_active by design — see
    // GHSA-52gv-wf4c-7qmm) turned that predicate into a no-op that
    // dropped every row and left the picker dropdowns blank.
    const availableUsers = users;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px] bg-slate-950 border-slate-800 text-white">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-xl">
                        <Shield className="h-5 w-5 text-primary" />
                        Manage Mission Team
                    </DialogTitle>
                    <DialogDescription className="text-slate-400">
                        Assign personnel and define their operational roles for this mission.
                    </DialogDescription>
                </DialogHeader>

                <div className="py-4 space-y-4">
                    <div className="flex items-center justify-between px-2">
                        <span className="text-sm font-medium text-slate-400 uppercase tracking-wider">Assigned Members ({assignments.length})</span>
                        <Button
                            onClick={handleAddUser}
                            variant="outline"
                            size="sm"
                            className="h-8 border-primary/30 bg-primary/10 text-primary hover:bg-primary/20"
                        >
                            <UserPlus className="h-4 w-4 mr-2" />
                            Add Member
                        </Button>
                    </div>

                    <ScrollArea className="h-[350px] pr-4">
                        <div className="space-y-3">
                            {assignments.map((assignment, index) => {
                                const user = users.find(u => u.id === assignment.user_id);
                                return (
                                    <div
                                        key={index}
                                        className="flex items-center gap-3 p-3 rounded-xl border border-slate-800 bg-slate-900/40 group transition-all hover:border-slate-700"
                                    >
                                        <UserAvatar
                                            user={user ? {
                                                id: user.id,
                                                username: user.username,
                                                full_name: user.full_name,
                                                profile_photo: user.profile_photo,
                                            } : undefined}
                                            className="h-9 w-9"
                                        />

                                        <div className="flex-1 grid grid-cols-2 gap-3 mt-1">
                                            <div className="space-y-1">
                                                <p className="text-[10px] uppercase font-bold text-slate-500 tracking-widest pl-1">Personnel</p>
                                                <Select
                                                    value={assignment.user_id}
                                                    onValueChange={(val) => handleUpdateAssignment(assignment.user_id, 'user_id', val)}
                                                >
                                                    <SelectTrigger className="h-9 bg-slate-950 border-slate-800 focus:ring-primary/50">
                                                        <SelectValue placeholder="Select user" />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                        {availableUsers.map(u => (
                                                            <SelectItem key={u.id} value={u.id}>
                                                                {u.full_name || u.username}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-1">
                                                <p className="text-[10px] uppercase font-bold text-slate-500 tracking-widest pl-1">Mission Role</p>
                                                <Select
                                                    value={assignment.role_id}
                                                    onValueChange={(val) => handleUpdateAssignment(assignment.user_id, 'role_id', val)}
                                                >
                                                    <SelectTrigger className="h-9 bg-slate-950 border-slate-800 focus:ring-primary/50">
                                                        <SelectValue placeholder="Select role" />
                                                    </SelectTrigger>
                                                    <SelectContent className="bg-slate-900 border-slate-800 text-white">
                                                        {roles.map(r => (
                                                            <SelectItem key={r.id} value={r.id}>
                                                                {r.name}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        </div>

                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => handleRemoveUser(assignment.user_id)}
                                            className="h-8 w-8 text-slate-500 hover:text-red-400 hover:bg-red-400/10 mt-4 self-center"
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                );
                            })}

                            {assignments.length === 0 && (
                                <div className="text-center py-10 border border-dashed border-slate-800 rounded-xl">
                                    <p className="text-slate-500 text-sm">No personnel assigned to this mission.</p>
                                </div>
                            )}
                        </div>
                    </ScrollArea>
                </div>

                <DialogFooter className="border-t border-slate-800 pt-4">
                    <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-slate-400 hover:text-white hover:bg-slate-800">
                        Cancel
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={updateEngagement.isPending}
                        className="bg-primary hover:bg-primary/90 min-w-[120px]"
                    >
                        {updateEngagement.isPending ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Saving Unit...
                            </>
                        ) : (
                            'Deploy Team'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
