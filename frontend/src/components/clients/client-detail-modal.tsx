'use client';

import { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Building2,
    Mail,
    UserCircle,
    StickyNote,
    Briefcase,
    ChevronRight,
    FolderTree,
    FileText,
    Shield,
    UserPlus,
    X,
    Loader2,
    Users,
} from 'lucide-react';
import { Client, ClientType } from '@/lib/types';
import { useClientAccess, useGrantClientAccess, useRevokeClientAccess, ClientAccessUser } from '@/lib/hooks/use-clients';
import { useUsers } from '@/lib/hooks/use-users';
import { UserAvatar } from '@/components/ui/user-avatar';
import { useAuthStore } from '@/stores/auth-store';
import { toast } from 'sonner';

interface ClientDetailModalProps {
    client: Client | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    clientTypes?: ClientType[];
    allClients?: Client[];
}

function buildBreadcrumb(client: Client, allClients: Client[]): Client[] {
    const chain: Client[] = [];
    let current: Client | undefined = client;
    while (current) {
        chain.unshift(current);
        current = allClients.find(c => c.id === current!.parent_id);
    }
    return chain;
}

/** Walk up the tree to find inherited access from ancestor clients */
function getInheritedAccess(
    client: Client,
    allClients: Client[],
    allAccessMap: Map<string, ClientAccessUser[]>
): { user: ClientAccessUser; fromClient: Client }[] {
    const inherited: { user: ClientAccessUser; fromClient: Client }[] = [];
    let current: Client | undefined = allClients.find(c => c.id === client.parent_id);
    while (current) {
        const grants = allAccessMap.get(current.id) || [];
        for (const u of grants) {
            inherited.push({ user: u, fromClient: current });
        }
        current = allClients.find(c => c.id === current!.parent_id);
    }
    return inherited;
}

export function ClientDetailModal({
    client,
    open,
    onOpenChange,
    clientTypes = [],
    allClients = [],
}: ClientDetailModalProps) {
    const [selectedUserId, setSelectedUserId] = useState<string>('');
    const user = useAuthStore((s) => s.user);
    const isAdmin = user?.role === 'admin' || user?.role === 'read_only_admin' || user?.role === 'team_lead';

    const { data: directAccess = [], isLoading: accessLoading } = useClientAccess(open && client ? client.id : null);
    const { data: allUsers = [] } = useUsers();
    const grantAccess = useGrantClientAccess();
    const revokeAccess = useRevokeClientAccess();

    if (!client) return null;

    const clientType = clientTypes.find(t => t.id === client.client_type_id);
    const breadcrumb = buildBreadcrumb(client, allClients);
    const children = allClients.filter(c => c.parent_id === client.id);

    // Users already granted (direct) — can't add them again
    const directUserIds = new Set(directAccess.map(a => a.user_id));
    const availableUsers = allUsers.filter(u => u.is_active && !directUserIds.has(u.id));

    const handleGrant = async () => {
        if (!selectedUserId || !client) return;
        try {
            await grantAccess.mutateAsync({ clientId: client.id, userId: selectedUserId });
            setSelectedUserId('');
            toast.success('Access granted');
        } catch (e: any) {
            toast.error(e.response?.data?.detail || 'Failed to grant access');
        }
    };

    const handleRevoke = async (userId: string) => {
        if (!client) return;
        try {
            await revokeAccess.mutateAsync({ clientId: client.id, userId });
            toast.success('Access revoked');
        } catch (e: any) {
            toast.error(e.response?.data?.detail || 'Failed to revoke access');
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg bg-slate-900 border-slate-800 max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                            <Building2 className="h-5 w-5 text-indigo-400" />
                        </div>
                        <div>
                            <span className="text-lg">{client.name}</span>
                            {clientType && (
                                <Badge
                                    variant="outline"
                                    className="ml-2 text-[10px] py-0.5 px-2 leading-normal"
                                    style={{
                                        borderColor: clientType.color,
                                        color: clientType.color,
                                        backgroundColor: `${clientType.color}10`,
                                    }}
                                >
                                    {clientType.name}
                                </Badge>
                            )}
                        </div>
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-5 py-2">
                    {/* Hierarchy Breadcrumb */}
                    {breadcrumb.length > 1 && (
                        <div className="space-y-2">
                            <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold flex items-center gap-1.5">
                                <FolderTree className="h-3 w-3" />
                                Hierarchy
                            </p>
                            <div className="flex items-center flex-wrap gap-1 px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                                {breadcrumb.map((item, idx) => {
                                    const isLast = idx === breadcrumb.length - 1;
                                    const type = clientTypes.find(t => t.id === item.client_type_id);
                                    return (
                                        <span key={item.id} className="flex items-center gap-1">
                                            {idx > 0 && <ChevronRight className="h-3 w-3 text-slate-600 shrink-0" />}
                                            <span className={`text-xs ${isLast ? 'text-white font-semibold' : 'text-slate-400'}`}>
                                                {item.name}
                                            </span>
                                            {type && (
                                                <span
                                                    className="text-[9px] px-1.5 py-0.5 rounded leading-normal"
                                                    style={{
                                                        color: type.color,
                                                        backgroundColor: `${type.color}15`,
                                                    }}
                                                >
                                                    {type.name}
                                                </span>
                                            )}
                                        </span>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Children */}
                    {children.length > 0 && (
                        <div className="space-y-2">
                            <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold flex items-center gap-1.5">
                                <FolderTree className="h-3 w-3" />
                                Sub-Clients ({children.length})
                            </p>
                            <div className="space-y-1 px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                                {children.map(child => {
                                    const childType = clientTypes.find(t => t.id === child.client_type_id);
                                    return (
                                        <div key={child.id} className="flex items-center gap-2 py-1">
                                            <Building2 className="h-3 w-3 text-slate-500" />
                                            <span className="text-sm text-slate-300">{child.name}</span>
                                            {childType && (
                                                <Badge
                                                    variant="outline"
                                                    className="text-[9px] py-0.5 px-2 leading-normal"
                                                    style={{
                                                        borderColor: childType.color,
                                                        color: childType.color,
                                                        backgroundColor: `${childType.color}10`,
                                                    }}
                                                >
                                                    {childType.name}
                                                </Badge>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Description */}
                    {client.description && (
                        <>
                            <Separator className="bg-slate-800" />
                            <div className="space-y-1.5">
                                <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold flex items-center gap-1.5">
                                    <FileText className="h-3 w-3" />
                                    Description
                                </p>
                                <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                                    {client.description}
                                </p>
                            </div>
                        </>
                    )}

                    <Separator className="bg-slate-800" />

                    {/* Contact Info */}
                    <div className="space-y-3">
                        <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Contact Information</p>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-800/40 border border-slate-700/40">
                                <UserCircle className="h-4 w-4 text-blue-400 shrink-0" />
                                <div className="min-w-0">
                                    <p className="text-[10px] text-slate-500 font-medium">Name</p>
                                    <p className="text-sm text-white truncate">{client.contact_name || '—'}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-800/40 border border-slate-700/40">
                                <Mail className="h-4 w-4 text-teal-400 shrink-0" />
                                <div className="min-w-0">
                                    <p className="text-[10px] text-slate-500 font-medium">Email</p>
                                    {client.contact_email ? (
                                        <a
                                            href={`mailto:${client.contact_email}`}
                                            className="text-sm text-teal-400 hover:text-teal-300 transition-colors truncate block"
                                        >
                                            {client.contact_email}
                                        </a>
                                    ) : (
                                        <p className="text-sm text-white">—</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Notes */}
                    {client.notes && (
                        <>
                            <Separator className="bg-slate-800" />
                            <div className="space-y-1.5">
                                <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold flex items-center gap-1.5">
                                    <StickyNote className="h-3 w-3" />
                                    Notes
                                </p>
                                <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                                    {client.notes}
                                </p>
                            </div>
                        </>
                    )}

                    {/* Engagement Count */}
                    {(client.engagement_count || 0) > 0 && (
                        <>
                            <Separator className="bg-slate-800" />
                            <div className="flex items-center gap-2 text-sm text-slate-400">
                                <Briefcase className="h-4 w-4" />
                                <span>{client.engagement_count} linked engagement{client.engagement_count !== 1 ? 's' : ''}</span>
                            </div>
                        </>
                    )}

                    {/* ━━━ Access Control Section (Admin only) ━━━ */}
                    {isAdmin && (
                        <>
                            <Separator className="bg-slate-800" />
                            <div className="space-y-3">
                                <p className="text-[10px] uppercase tracking-wider text-slate-500 font-bold flex items-center gap-1.5">
                                    <Shield className="h-3 w-3" />
                                    Read Access
                                </p>

                                {/* Add user */}
                                <div className="flex gap-2">
                                    <Select value={selectedUserId} onValueChange={setSelectedUserId}>
                                        <SelectTrigger className="flex-1 bg-slate-800/50 border-slate-700 text-white h-9 text-sm">
                                            <SelectValue placeholder="Select a user to grant access..." />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {availableUsers.map(u => (
                                                <SelectItem key={u.id} value={u.id}>
                                                    <span className="flex items-center gap-2">
                                                        <Users className="h-3 w-3 text-slate-400" />
                                                        {u.full_name || u.username}
                                                        <span className="text-slate-500 text-xs">@{u.username}</span>
                                                    </span>
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <Button
                                        size="sm"
                                        onClick={handleGrant}
                                        disabled={!selectedUserId || grantAccess.isPending}
                                        className="bg-primary hover:bg-primary/90 h-9 px-3"
                                    >
                                        {grantAccess.isPending ? (
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                            <UserPlus className="h-4 w-4" />
                                        )}
                                    </Button>
                                </div>

                                {/* Direct access users */}
                                {accessLoading ? (
                                    <div className="flex justify-center py-3">
                                        <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
                                    </div>
                                ) : directAccess.length > 0 ? (
                                    <div className="space-y-1">
                                        {directAccess.map(access => (
                                            <div
                                                key={access.user_id}
                                                className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/40 border border-slate-700/40 group"
                                            >
                                                <div className="flex items-center gap-2.5 min-w-0">
                                                    <UserAvatar
                                                        user={{
                                                            id: access.user_id,
                                                            username: access.username,
                                                            full_name: access.full_name,
                                                            profile_photo: access.profile_photo,
                                                        }}
                                                        className="h-7 w-7 text-[10px] shrink-0"
                                                    />
                                                    <div className="min-w-0">
                                                        <p className="text-sm text-white truncate">
                                                            {access.full_name || access.username}
                                                        </p>
                                                        <p className="text-[10px] text-slate-500 truncate">
                                                            @{access.username}
                                                        </p>
                                                    </div>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-7 w-7 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                                                    onClick={() => handleRevoke(access.user_id)}
                                                    disabled={revokeAccess.isPending}
                                                >
                                                    <X className="h-3.5 w-3.5" />
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-xs text-slate-500 text-center py-2">
                                        No users have been granted direct read access to this client.
                                    </p>
                                )}

                                {/* Inheritance note */}
                                {children.length > 0 && directAccess.length > 0 && (
                                    <p className="text-[10px] text-slate-500 flex items-center gap-1">
                                        <FolderTree className="h-3 w-3 shrink-0" />
                                        Access is inherited — users above also have read access to all sub-clients and their engagements.
                                    </p>
                                )}
                            </div>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
