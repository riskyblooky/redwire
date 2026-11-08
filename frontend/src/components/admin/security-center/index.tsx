'use client';

import { useState } from 'react';
import { Activity, Globe, KeyRound, ListChecks, ScrollText, ShieldCheck } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuthStore } from '@/stores/auth-store';
import { useGlobalPermissions } from '@/lib/hooks/use-permissions';
import { SecurityOverviewTab } from './overview-tab';
import { SigninsTab } from './signins-tab';
import { TrafficTab } from './traffic-tab';
import { AccountsTab } from './accounts-tab';
import { PostureTab } from './posture-tab';
import { AuditTab } from './audit-tab';

export type SecurityTab = 'overview' | 'signins' | 'traffic' | 'accounts' | 'posture' | 'audit';

export interface SecurityNav {
    go: (tab: SecurityTab, opts?: { ip?: string }) => void;
}

const TRIGGER = 'rounded-lg px-3 py-1.5 text-xs font-semibold gap-1.5 data-[state=active]:bg-primary/10 data-[state=active]:text-primary hover:text-foreground';

/** Admin → Security: sign-ins, web traffic, accounts & tokens, posture, audit. */
export function SecurityCenter() {
    const { user } = useAuthStore();
    const { data: perms = [] } = useGlobalPermissions();
    const canManage = user?.role === 'admin' || perms.includes('manage_security_center');
    const [tab, setTab] = useState<SecurityTab>('overview');
    const [ip, setIp] = useState<string | undefined>();

    const nav: SecurityNav = {
        go: (t, opts) => {
            setIp(opts?.ip);
            setTab(t);
        },
    };

    return (
        <Tabs value={tab} onValueChange={(v) => { setIp(undefined); setTab(v as SecurityTab); }} className="space-y-4">
            <TabsList className="h-auto flex-wrap gap-0.5 rounded-xl border border-border bg-background/40 p-1">
                <TabsTrigger value="overview" className={TRIGGER}><ShieldCheck className="h-3.5 w-3.5" /> Overview</TabsTrigger>
                <TabsTrigger value="signins" className={TRIGGER}><Activity className="h-3.5 w-3.5" /> Sign-ins</TabsTrigger>
                <TabsTrigger value="traffic" className={TRIGGER}><Globe className="h-3.5 w-3.5" /> Web traffic</TabsTrigger>
                <TabsTrigger value="accounts" className={TRIGGER}><KeyRound className="h-3.5 w-3.5" /> Accounts &amp; tokens</TabsTrigger>
                <TabsTrigger value="posture" className={TRIGGER}><ListChecks className="h-3.5 w-3.5" /> Posture</TabsTrigger>
                <TabsTrigger value="audit" className={TRIGGER}><ScrollText className="h-3.5 w-3.5" /> Admin audit</TabsTrigger>
            </TabsList>

            <TabsContent value="overview"><SecurityOverviewTab nav={nav} /></TabsContent>
            <TabsContent value="signins"><SigninsTab initialIp={ip} key={`s-${ip ?? ''}`} /></TabsContent>
            <TabsContent value="traffic"><TrafficTab initialIp={ip} key={`t-${ip ?? ''}`} /></TabsContent>
            <TabsContent value="accounts"><AccountsTab canManage={canManage} /></TabsContent>
            <TabsContent value="posture"><PostureTab /></TabsContent>
            <TabsContent value="audit"><AuditTab canManage={canManage} /></TabsContent>
        </Tabs>
    );
}
