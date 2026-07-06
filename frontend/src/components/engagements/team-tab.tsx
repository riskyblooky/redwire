/**
 * team-tab.tsx — Engagement Team Tab
 *
 * Displays the list of personnel assigned to the engagement in a table
 * with columns for name (with avatar), mission role (engagement-specific),
 * and platform role (admin/operator). The "Manage Team" button opens the
 * TeamManagementDialog (rendered at the page level).
 *
 * This is a presentational component — it receives the engagement object
 * and callbacks as props; it does not fetch data or manage dialog state.
 */
'use client';

import { useState } from 'react';
import { Users, Mail, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UserAvatar } from '@/components/ui/user-avatar';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { toast } from 'sonner';

interface TeamTabProps {
    engagement: any;
    canManageMembers: boolean;
    onOpenTeamDialog: () => void;
}

export function TeamTab({ engagement, canManageMembers, onOpenTeamDialog }: TeamTabProps) {
    const [emailsCopied, setEmailsCopied] = useState(false);

    const emails = (engagement.assigned_users ?? [])
        .map((u: any) => u.email)
        .filter(Boolean) as string[];

    const handleCopyEmails = async () => {
        if (emails.length === 0) return;
        await navigator.clipboard.writeText(emails.join(', '));
        toast.success(`${emails.length} email${emails.length === 1 ? '' : 's'} copied to clipboard`);
        setEmailsCopied(true);
        setTimeout(() => setEmailsCopied(false), 1500);
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle className="text-white">Assigned Personnel</CardTitle>
                    <CardDescription>Team members and their specific mission roles</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                    {emails.length > 0 && (
                        <Button
                            onClick={handleCopyEmails}
                            variant="outline"
                            size="sm"
                            className="h-9 border-teal-500/30 bg-teal-500/10 text-teal-400 hover:bg-teal-500/20"
                        >
                            {emailsCopied
                                ? <><Check className="h-4 w-4 mr-2" />Copied!</>
                                : <><Mail className="h-4 w-4 mr-2" />Copy Emails</>}
                        </Button>
                    )}
                    {canManageMembers && (
                        <Button
                            onClick={onOpenTeamDialog}
                            variant="outline"
                            size="sm"
                            className="h-9 border-primary/30 bg-primary/10 text-primary hover:bg-primary/20"
                        >
                            <Users className="h-4 w-4 mr-2" />
                            Manage Team
                        </Button>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                <Table>
                    <TableHeader>
                        <TableRow className="border-slate-800">
                            <TableHead className="text-slate-400">Personnel</TableHead>
                            <TableHead className="text-slate-400">Mission Role</TableHead>
                            <TableHead className="text-slate-400">Platform Role</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {(!engagement.assignment_details || engagement.assignment_details.length === 0) ? (
                            <TableRow>
                                <TableCell colSpan={3} className="h-24 text-center text-slate-500 italic">
                                    No personnel assigned to this mission
                                </TableCell>
                            </TableRow>
                        ) : (
                            engagement.assignment_details.map((assignment: any) => {
                                const u = engagement.assigned_users?.find((user: any) => user.id === assignment.user_id);
                                const displayName = u?.full_name || u?.username || `User ${assignment.user_id.slice(0, 8)}`;
                                const initials = u?.full_name
                                    ? u.full_name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)
                                    : u?.username?.slice(0, 2).toUpperCase() || 'U';

                                return (
                                    <TableRow key={assignment.user_id} className="border-slate-800 hover:bg-slate-800/30">
                                        <TableCell className="font-medium text-slate-200">
                                            <div className="flex items-center gap-3">
                                                <UserAvatar user={u} className="h-8 w-8" />
                                                {displayName}
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <Badge className={cn(
                                                "px-2 py-0.5",
                                                assignment.role?.name === 'Engagement Lead'
                                                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                                    : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                                            )}>
                                                {assignment.role?.name || 'Assigned'}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-slate-400 text-sm italic capitalize">
                                            {u?.role || 'operator'}
                                        </TableCell>
                                    </TableRow>
                                );
                            })
                        )}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );
}
