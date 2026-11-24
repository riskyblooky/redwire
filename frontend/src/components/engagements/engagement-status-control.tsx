'use client';

// The status pill in the engagement header: a select for users who may
// change the status, a badge for everyone else.

import { useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getErrorMessage } from '@/components/ui/confirm-dialog';
import { cn } from '@/lib/utils';
import { useUpdateEngagement, type Engagement } from '@/lib/hooks/use-engagements';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/hooks/use-auth';
import { ENGAGEMENT_STATUSES, ENGAGEMENT_STATUS_BADGE, ENGAGEMENT_STATUS_BADGE_FALLBACK } from '@/lib/engagement-status';





interface EngagementStatusControlProps {
    engagement: Engagement;
    /** engagement_edit on this engagement (useCanEdit). */
    canEdit: boolean;
}

export function EngagementStatusControl({ engagement, canEdit }: EngagementStatusControlProps) {
    const updateEngagement = useUpdateEngagement();
    const { user: currentUser } = useAuthStore();
    const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

    // Who may change the status is what the backend accepts: engagement_edit,
    // except that a COMPLETED engagement is locked to admins / team leads
    // (GHSA-2gmw-jf4c-8q5g). The control used to be shown by role only.
    const canChangeStatus = canEdit && (
        engagement.status !== 'COMPLETED'
        || currentUser?.role === UserRole.ADMIN || currentUser?.role === UserRole.TEAM_LEAD
    );
    // A PROPOSED engagement must show its own status (the Select rendered
    // blank for a value not in its list); it's only offered while current.
    const statusOptions = ENGAGEMENT_STATUSES.filter(
        s => s.value !== 'PROPOSED' || engagement.status === 'PROPOSED');

    const handleStatusChange = async (newStatus: string) => {
        setIsUpdatingStatus(true);
        try {
            await updateEngagement.mutateAsync({ id: engagement.id, status: newStatus });
        } catch (error) {
            toast.error(getErrorMessage(error, 'Failed to update engagement status'));
        } finally {
            setIsUpdatingStatus(false);
        }
    };

    return canChangeStatus ? (
            <Select
                value={engagement.status}
                onValueChange={handleStatusChange}
                disabled={isUpdatingStatus}
            >
                <SelectTrigger className={cn(
                    "h-7 w-fit min-w-[100px] px-2 py-0 border-none shadow-none focus:ring-0 text-[11px] font-bold uppercase",
                    ENGAGEMENT_STATUS_BADGE[engagement.status] || ENGAGEMENT_STATUS_BADGE_FALLBACK
                )}>
                    {isUpdatingStatus ? (
                        <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    ) : (
                        <SelectValue />
                    )}
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                    {statusOptions.map((s) => (
                        <SelectItem
                            key={s.value}
                            value={s.value}
                            className={cn("my-1 mx-1 rounded-md font-medium text-[11px]", ENGAGEMENT_STATUS_BADGE[s.value])}
                        >
                            {s.label}
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        ) : (
            <Badge className={cn("px-2 py-0.5", ENGAGEMENT_STATUS_BADGE[engagement.status])}>
                {engagement.status.replace('_', ' ')}
            </Badge>
        );
}
