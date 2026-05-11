'use client';

import { Check, UserPlus, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useUsers } from '@/lib/hooks/use-users';
import { ScrollArea } from '@/components/ui/scroll-area';

interface UserAssignmentFieldProps {
    selectedUserIds: string[];
    onChange: (userIds: string[]) => void;
}

export function UserAssignmentField({ selectedUserIds, onChange }: UserAssignmentFieldProps) {
    const { data: users = [] } = useUsers();

    const toggleUser = (userId: string) => {
        if (selectedUserIds.includes(userId)) {
            onChange(selectedUserIds.filter(id => id !== userId));
        } else {
            onChange([...selectedUserIds, userId]);
        }
    };

    const selectedUsers = users.filter(u => selectedUserIds.includes(u.id));

    return (
        <div className="space-y-3">
            <div className="flex flex-wrap gap-2 min-h-[40px] p-2 rounded-lg border border-slate-700 bg-slate-800/30">
                {selectedUsers.length === 0 && (
                    <span className="text-slate-500 text-sm py-1 px-2">No users assigned</span>
                )}
                {selectedUsers.map(user => (
                    <Badge key={user.id} className="bg-purple-500/10 text-purple-400 border-purple-500/20 py-1 pl-2 pr-1 gap-1">
                        {user.full_name || user.username}
                        <button
                            type="button"
                            onClick={() => toggleUser(user.id)}
                            className="hover:bg-primary/20 rounded-full p-0.5"
                        >
                            <X className="h-3 w-3" />
                        </button>
                    </Badge>
                ))}
            </div>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="border-slate-700 bg-slate-800/50 hover:bg-slate-800">
                        <UserPlus className="h-4 w-4 mr-2" /> Assign Operators
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-64 bg-slate-900 border-slate-800 text-white">
                    <DropdownMenuLabel>Search Users</DropdownMenuLabel>
                    <DropdownMenuSeparator className="bg-slate-800" />
                    <ScrollArea className="h-64">
                        {users.map(user => (
                            <DropdownMenuItem
                                key={user.id}
                                onClick={(e) => {
                                    e.preventDefault();
                                    toggleUser(user.id);
                                }}
                                className="flex items-center justify-between cursor-pointer hover:bg-slate-800"
                            >
                                <div className="flex flex-col">
                                    <span className="text-sm font-medium">{user.full_name || user.username}</span>
                                    <span className="text-[10px] text-slate-500 uppercase">{user.role}</span>
                                </div>
                                {selectedUserIds.includes(user.id) && <Check className="h-4 w-4 text-primary" />}
                            </DropdownMenuItem>
                        ))}
                    </ScrollArea>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
