'use client';

import { ReactNode, useRef, useCallback, useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { ErrorBoundary } from '@/components/ui/error-boundary';
import { useAuthStore } from '@/stores/auth-store';
import { UserRole } from '@/lib/types';
import {
    LayoutDashboard,
    Briefcase,
    Calendar,
    Settings,
    Shield,
    LogOut,
    User,
    ChevronLeft,
    BarChart,
    BookOpen,
    Tags,
    Building2,
    Search,
    Lock,
    Eye,
    EyeOff,
    Loader2,
    Bell,
    Check,
    CheckCheck,
    ExternalLink,
    BellRing,
    Zap,
    ClipboardCheck,
    GanttChart,
    Radar,
    Server,
    Upload,
    Plug,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { cn, getAvatarUrl } from '@/lib/utils';
import EngagementSelector from '@/components/engagement-selector';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import api, { startProactiveRefresh } from '@/lib/api';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useNotifications, useUnreadCount, useMarkRead, useMarkAllRead, useClearAllNotifications, useNotificationPreferences, useUpdateNotificationPreferences } from '@/lib/hooks/use-notifications';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface NavItem {
    title: string;
    href: string;
    icon: any;
    badge?: string;
    adminOnly?: boolean;
    managerOnly?: boolean; // admin or team_lead
}

const navItems: NavItem[] = [
    { title: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { title: 'Engagements', href: '/engagements', icon: Briefcase },
    { title: 'Calendar', href: '/calendar', icon: Calendar },
    { title: 'Planning', href: '/planning', icon: GanttChart, managerOnly: true },
    { title: 'Stats', href: '/stats', icon: BarChart },
    { title: 'Remediation', href: '/remediation', icon: ClipboardCheck },
    { title: 'Intelligence', href: '/intelligence', icon: Radar },
    { title: 'Import', href: '/imports', icon: Upload },
    { title: 'Infrastructure', href: '/infrastructure', icon: Server },
    { title: 'Templates', href: '/templates', icon: BookOpen },
    { title: 'Tags', href: '/tags', icon: Tags },
    { title: 'Automations', href: '/automations', icon: Zap, managerOnly: true },
    { title: 'Clients', href: '/clients', icon: Building2, managerOnly: true },
    { title: 'Admin', href: '/admin', icon: Settings, adminOnly: true },
];

interface DashboardLayoutProps {
    children: ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
    const pathname = usePathname();
    const router = useRouter();
    const { user, logout, mustChangePassword, clearMustChangePassword } = useAuthStore();
    const [collapsed, setCollapsed] = useState(false);
    const [hoverExpanded, setHoverExpanded] = useState(false);
    const hoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [headerSearch, setHeaderSearch] = useState('');
    const searchInputRef = useRef<HTMLInputElement>(null);

    // Force password change state
    const [fpCurrentPassword, setFpCurrentPassword] = useState('');
    const [fpNewPassword, setFpNewPassword] = useState('');
    const [fpConfirmPassword, setFpConfirmPassword] = useState('');
    const [fpShowCurrent, setFpShowCurrent] = useState(false);
    const [fpShowNew, setFpShowNew] = useState(false);
    const [fpError, setFpError] = useState('');
    const [fpLoading, setFpLoading] = useState(false);

    const handleForceChangePassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setFpError('');

        if (fpNewPassword.length < 8) {
            setFpError('New password must be at least 8 characters');
            return;
        }
        if (fpNewPassword !== fpConfirmPassword) {
            setFpError('Passwords do not match');
            return;
        }

        setFpLoading(true);
        try {
            const response = await api.post('/auth/force-change-password', {
                current_password: fpCurrentPassword,
                new_password: fpNewPassword,
            });
            const { access_token, refresh_token } = response.data;
            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', refresh_token);
            document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
            startProactiveRefresh();
            clearMustChangePassword();
            // Update user object in store
            const userResponse = await api.get('/auth/me');
            useAuthStore.getState().setUser(userResponse.data);
            toast.success('Password changed successfully');
        } catch (err: any) {
            setFpError(err?.response?.data?.detail || 'Failed to change password');
        } finally {
            setFpLoading(false);
        }
    };

    // Visual state: expanded if manually open, OR if collapsed but hovered
    const expanded = !collapsed || hoverExpanded;

    const handleMouseEnter = () => {
        if (!collapsed) return;
        hoverTimeout.current = setTimeout(() => setHoverExpanded(true), 300);
    };

    const handleMouseLeave = () => {
        if (hoverTimeout.current) {
            clearTimeout(hoverTimeout.current);
            hoverTimeout.current = null;
        }
        setHoverExpanded(false);
    };

    // Notification data
    const queryClient = useQueryClient();
    const { data: notifications = [] } = useNotifications(30);
    const { data: unreadCount = 0 } = useUnreadCount();
    const markRead = useMarkRead();
    const markAllRead = useMarkAllRead();
    const clearAll = useClearAllNotifications();
    const [notifOpen, setNotifOpen] = useState(false);
    const [notifSettingsOpen, setNotifSettingsOpen] = useState(false);
    const { data: notifPrefs = [] } = useNotificationPreferences();
    const updateNotifPrefs = useUpdateNotificationPreferences();

    const handleNotifPrefToggle = (eventType: string, field: 'site_muted' | 'email_muted', currentValue: boolean) => {
        const updated = notifPrefs.map((p) => ({
            event_type: p.event_type,
            site_muted: field === 'site_muted' && p.event_type === eventType ? !currentValue : p.site_muted,
            email_muted: field === 'email_muted' && p.event_type === eventType ? !currentValue : p.email_muted,
        }));
        updateNotifPrefs.mutate(updated, {
            onSuccess: () => toast.success('Notification preferences saved'),
        });
    };

    // Listen for user-level notifications via WebSocket
    useCollaboration({
        resourceType: 'user',
        resourceId: user?.id || '',
        enabled: !!user?.id,
        onMessage: (data) => {
            if (data.type === 'notification') {
                // Refresh notification queries (list + unread count badge)
                queryClient.invalidateQueries({ queryKey: ['notifications'] });
                const n = data.notification;
                toast.info(n.title, {
                    description: n.message,
                    action: n.link ? {
                        label: 'View',
                        onClick: () => router.push(n.link),
                    } : undefined,
                    duration: 6000,
                });
            }
            // Backward compat for team_member_added without notification system
            if (data.type === 'team_member_added') {
                queryClient.invalidateQueries({ queryKey: ['notifications'] });
            }
        },
    });

    const formatTimeAgo = (dateStr: string) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    };

    const handleNotificationClick = (notif: typeof notifications[0]) => {
        if (!notif.is_read) {
            markRead.mutate(notif.id);
        }
        if (notif.link) {
            router.push(notif.link);
        }
        setNotifOpen(false);
    };

    const getEventIcon = (eventType: string) => {
        switch (eventType) {
            case 'engagement_assigned': return '👥';
            case 'engagement_removed': return '🚫';
            case 'finding_created': return '🔍';
            case 'finding_status_changed': return '🔄';
            case 'engagement_status_changed': return '📋';
            case 'password_reset': return '🔑';
            case 'mention': return '💬';
            default: return '🔔';
        }
    };

    const isAdmin = user?.role === UserRole.ADMIN || user?.role === UserRole.READ_ONLY_ADMIN;
    const isManager = user?.role === UserRole.ADMIN || user?.role === UserRole.READ_ONLY_ADMIN || user?.role === UserRole.TEAM_LEAD;

    const filteredNavItems = navItems.filter(item => {
        if (item.adminOnly && !isAdmin) return false;
        if (item.managerOnly && !isManager) return false;
        return true;
    });

    // Fetch plugin nav items
    const { data: pluginNavItems = [] } = useQuery({
        queryKey: ['plugin-nav-items'],
        queryFn: async () => {
            try {
                const { data } = await api.get('/plugins/nav-items');
                return data as { label: string; path: string; icon?: string; plugin_id: string; plugin_name: string }[];
            } catch { return []; }
        },
        staleTime: 60_000,
    });

    const getUserInitials = () => {
        if (!user) return 'U';
        if (user.full_name) {
            const names = user.full_name.split(' ');
            return names.map(n => n[0]).join('').toUpperCase().slice(0, 2);
        }
        return user.username.slice(0, 2).toUpperCase();
    };

    // Ctrl+K / Cmd+K to focus search
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                searchInputRef.current?.focus();
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    const handleHeaderSearch = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        if (headerSearch.trim()) {
            router.push(`/search?q=${encodeURIComponent(headerSearch.trim())}`);
            setHeaderSearch('');
        }
    }, [headerSearch, router]);

    return (
        <div className="flex h-screen overflow-hidden bg-slate-950">
            {/* Sidebar */}
            <aside
                className={cn(
                    "flex flex-col border-r border-slate-800 bg-slate-900 transition-all duration-300",
                    expanded ? "w-64" : "w-16"
                )}
                onMouseEnter={handleMouseEnter}
                onMouseLeave={handleMouseLeave}
            >
                {/* Logo/Header */}
                <div className="flex h-16 items-center justify-between px-4 border-b border-slate-800">
                    {expanded && (
                        <div className="flex items-center gap-2">
                            <img src="/redwire.png" alt="RedWire" className="h-8" />
                        </div>
                    )}
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setCollapsed(!collapsed)}
                        className="text-slate-400 hover:text-white hover:bg-slate-800"
                    >
                        <ChevronLeft className={cn("h-5 w-5 transition-transform", collapsed && "rotate-180")} />
                    </Button>
                </div>

                {/* Navigation */}
                <ScrollArea className="flex-1 px-3 py-4">
                    <nav className="space-y-1">
                        {filteredNavItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = pathname === item.href || pathname.startsWith(item.href + '/');

                            return (
                                <Link key={item.href} href={item.href}>
                                    <div
                                        className={cn(
                                            "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                                            isActive
                                                ? "bg-primary hover:bg-primary/90 text-white shadow-lg"
                                                : "text-slate-400 hover:bg-slate-800 hover:text-white"
                                        )}
                                    >
                                        <Icon className="h-5 w-5 shrink-0" />
                                        {expanded && (
                                            <>
                                                <span className="flex-1">{item.title}</span>
                                                {item.badge && (
                                                    <Badge variant="secondary" className="ml-auto">
                                                        {item.badge}
                                                    </Badge>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </Link>
                            );
                        })}

                        {/* Plugin nav items */}
                        {pluginNavItems.length > 0 && (
                            <>
                                <div className="my-2 border-t border-slate-800/50" />
                                {expanded && (
                                    <span className="px-3 text-[10px] font-semibold tracking-wider text-slate-600 uppercase">Plugins</span>
                                )}
                                {pluginNavItems.map((item) => {
                                    const isActive = pathname === item.path || pathname.startsWith(item.path + '/');

                                    return (
                                        <Link key={item.path} href={item.path}>
                                            <div
                                                className={cn(
                                                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                                                    isActive
                                                        ? "bg-emerald-600 hover:bg-emerald-700 text-white shadow-lg"
                                                        : "text-slate-400 hover:bg-slate-800 hover:text-white"
                                                )}
                                            >
                                                <Plug className="h-5 w-5 shrink-0" />
                                                {expanded && (
                                                    <span className="flex-1">{item.label}</span>
                                                )}
                                            </div>
                                        </Link>
                                    );
                                })}
                            </>
                        )}
                    </nav>
                </ScrollArea>

                {/* User Profile */}
                <div className="border-t border-slate-800 p-3">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button
                                variant="ghost"
                                className={cn(
                                    "w-full justify-start gap-3 hover:bg-slate-800",
                                    collapsed && "justify-center"
                                )}
                            >
                                <Avatar className="h-8 w-8">
                                    {user?.profile_photo ? (
                                        <AvatarImage
                                            src={getAvatarUrl(user.profile_photo)}
                                            alt={user?.full_name || user?.username}
                                        />
                                    ) : null}
                                    <AvatarFallback className="bg-linear-to-br from-purple-500 to-pink-500 text-white text-xs">
                                        {getUserInitials()}
                                    </AvatarFallback>
                                </Avatar>
                                {expanded && (
                                    <div className="flex flex-1 flex-col items-start text-left">
                                        <span className="text-sm font-medium text-white">
                                            {user?.full_name || user?.username || 'User'}
                                        </span>
                                        <span className="text-xs text-slate-400 capitalize">
                                            {user?.role || 'operator'}
                                        </span>
                                    </div>
                                )}
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                            <DropdownMenuLabel>My Account</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem asChild>
                                <Link href="/profile" className="flex w-full items-center">
                                    <User className="mr-2 h-4 w-4" />
                                    Profile
                                </Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setNotifSettingsOpen(true)}>
                                <Bell className="mr-2 h-4 w-4" />
                                Notification Settings
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={logout} className="text-red-400">
                                <LogOut className="mr-2 h-4 w-4" />
                                Logout
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </aside>

            {/* Main Content Area */}
            <div className="flex flex-1 flex-col min-w-0">
                {/* Header Bar */}
                <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
                    <div className="flex items-center gap-4">
                        <EngagementSelector />
                    </div>
                    <div className="flex items-center gap-3">
                        <form onSubmit={handleHeaderSearch} className="flex items-center">
                            <div className="relative">
                                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
                                <Input
                                    ref={searchInputRef}
                                    value={headerSearch}
                                    onChange={(e) => setHeaderSearch(e.target.value)}
                                    placeholder="Search... (Ctrl+K)"
                                    className="w-64 pl-8 h-9 bg-slate-900/50 border-slate-800 text-sm text-white placeholder:text-slate-500 focus:border-primary/50 focus:ring-primary/20"
                                />
                            </div>
                        </form>

                        {/* Notification Bell */}
                        <Popover open={notifOpen} onOpenChange={setNotifOpen}>
                            <PopoverTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="relative text-slate-400 hover:text-white hover:bg-slate-800"
                                >
                                    <Bell className="h-5 w-5" />
                                    {unreadCount > 0 && (
                                        <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                                            {unreadCount > 99 ? '99+' : unreadCount}
                                        </span>
                                    )}
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent
                                align="end"
                                className="w-96 p-0 bg-slate-900 border-slate-700 flex flex-col max-h-[480px]"
                                sideOffset={8}
                            >
                                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 shrink-0">
                                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                                        <BellRing className="h-4 w-4" />
                                        Notifications
                                        {unreadCount > 0 && (
                                            <Badge variant="secondary" className="bg-red-500/20 text-red-400 text-xs ml-1">
                                                {unreadCount}
                                            </Badge>
                                        )}
                                    </h3>
                                    {unreadCount > 0 && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="text-xs text-slate-400 hover:text-white h-7"
                                            onClick={() => markAllRead.mutate()}
                                        >
                                            <CheckCheck className="h-3 w-3 mr-1" />
                                            Mark all read
                                        </Button>
                                    )}
                                </div>
                                <div className="flex-1 overflow-y-auto min-h-0">
                                    {notifications.length === 0 ? (
                                        <div className="flex flex-col items-center justify-center py-8 text-slate-500">
                                            <Bell className="h-8 w-8 mb-2 opacity-50" />
                                            <p className="text-sm">No notifications yet</p>
                                        </div>
                                    ) : (
                                        <div className="divide-y divide-slate-800/50">
                                            {notifications.map((notif) => (
                                                <button
                                                    key={notif.id}
                                                    onClick={() => handleNotificationClick(notif)}
                                                    className={cn(
                                                        "w-full text-left px-4 py-3 hover:bg-slate-800/50 transition-colors flex gap-3 items-start",
                                                        !notif.is_read && "bg-slate-800/30"
                                                    )}
                                                >
                                                    {!notif.is_read ? (
                                                        <span className="h-2.5 w-2.5 rounded-full bg-primary shrink-0 mt-1.5" />
                                                    ) : (
                                                        <span className="h-2.5 w-2.5 shrink-0" />
                                                    )}
                                                    <span className="text-lg shrink-0">{getEventIcon(notif.event_type)}</span>
                                                    <div className="flex-1 min-w-0">
                                                        <p className={cn(
                                                            "text-sm truncate",
                                                            notif.is_read ? "text-slate-400" : "text-white font-medium"
                                                        )}>
                                                            {notif.title}
                                                        </p>
                                                        {notif.message && (
                                                            <p className="text-xs text-slate-500 truncate mt-0.5">
                                                                {notif.message}
                                                            </p>
                                                        )}
                                                        <p className="text-xs text-slate-600 mt-1">
                                                            {formatTimeAgo(notif.created_at)}
                                                        </p>
                                                    </div>
                                                    {notif.link && (
                                                        <ExternalLink className="h-3.5 w-3.5 text-slate-600 shrink-0 mt-1" />
                                                    )}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                {notifications.length > 0 && (
                                    <div className="border-t border-slate-800 px-4 py-2 flex items-center justify-between shrink-0">
                                        <span className="text-[10px] text-slate-600">
                                            Showing last {notifications.length}
                                        </span>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="text-[10px] text-red-400 hover:text-red-300 hover:bg-red-500/10 h-6 px-2"
                                            onClick={() => { clearAll.mutate(); setNotifOpen(false); }}
                                        >
                                            Clear all
                                        </Button>
                                    </div>
                                )}
                            </PopoverContent>
                        </Popover>
                    </div>
                </header>

                {/* Page Content */}
                <main className="flex-1 overflow-y-auto overflow-x-hidden">
                    <ErrorBoundary>
                        {children}
                    </ErrorBoundary>
                </main>
            </div>
            {/* Force Password Change Modal */}
            {mustChangePassword && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm">
                    <div className="w-full max-w-md mx-4">
                        <div className="rounded-xl border border-slate-700 bg-slate-900 shadow-2xl p-8">
                            <div className="flex flex-col items-center gap-3 mb-6">
                                <div className="p-3 rounded-full bg-amber-500/10">
                                    <Lock className="h-8 w-8 text-amber-400" />
                                </div>
                                <h2 className="text-xl font-bold text-white">Password Change Required</h2>
                                <p className="text-sm text-slate-400 text-center">
                                    For security, you must change your password before continuing.
                                </p>
                            </div>

                            <form onSubmit={handleForceChangePassword} className="space-y-4">
                                <div className="space-y-2">
                                    <Label className="text-slate-300 text-sm">Current Password</Label>
                                    <div className="relative">
                                        <Input
                                            type={fpShowCurrent ? 'text' : 'password'}
                                            value={fpCurrentPassword}
                                            onChange={e => setFpCurrentPassword(e.target.value)}
                                            required
                                            className="bg-slate-800/50 border-slate-700 text-white pr-10"
                                            placeholder="Enter current password"
                                        />
                                        <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white" onClick={() => setFpShowCurrent(!fpShowCurrent)}>
                                            {fpShowCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </button>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label className="text-slate-300 text-sm">New Password</Label>
                                    <div className="relative">
                                        <Input
                                            type={fpShowNew ? 'text' : 'password'}
                                            value={fpNewPassword}
                                            onChange={e => setFpNewPassword(e.target.value)}
                                            required
                                            minLength={8}
                                            className="bg-slate-800/50 border-slate-700 text-white pr-10"
                                            placeholder="Min 8 characters"
                                        />
                                        <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white" onClick={() => setFpShowNew(!fpShowNew)}>
                                            {fpShowNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </button>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label className="text-slate-300 text-sm">Confirm New Password</Label>
                                    <Input
                                        type="password"
                                        value={fpConfirmPassword}
                                        onChange={e => setFpConfirmPassword(e.target.value)}
                                        required
                                        className="bg-slate-800/50 border-slate-700 text-white"
                                        placeholder="Re-enter new password"
                                    />
                                </div>

                                {fpError && (
                                    <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                                        {fpError}
                                    </p>
                                )}

                                <Button
                                    type="submit"
                                    disabled={fpLoading || !fpCurrentPassword || !fpNewPassword || !fpConfirmPassword}
                                    className="w-full bg-amber-600 hover:bg-amber-700 text-white"
                                >
                                    {fpLoading ? (
                                        <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Changing Password...</>
                                    ) : (
                                        'Change Password'
                                    )}
                                </Button>
                            </form>
                        </div>
                    </div>
                </div>
            )}

            {/* Notification Settings Modal */}
            <Dialog open={notifSettingsOpen} onOpenChange={setNotifSettingsOpen}>
                <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <BellRing className="h-5 w-5 text-blue-500" />
                            Notification Settings
                        </DialogTitle>
                        <DialogDescription>
                            Choose which events you want to be notified about
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-1 mt-2">
                        <div className="flex items-center text-xs text-slate-500 uppercase tracking-wider mb-3 px-1">
                            <span className="flex-1">Event</span>
                            <span className="w-20 text-center">Site</span>
                            <span className="w-20 text-center">Email</span>
                        </div>
                        {notifPrefs.map((pref) => (
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
                                        onCheckedChange={() => handleNotifPrefToggle(pref.event_type, 'site_muted', pref.site_muted)}
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
                </DialogContent>
            </Dialog>
        </div>
    );
}
