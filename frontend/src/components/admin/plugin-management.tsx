'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { toast } from 'sonner';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
    Plug,
    Settings,
    Globe,
    Zap,
    LayoutGrid,
    Navigation,
    Eye,
    EyeOff,
    Save,
    AlertTriangle,
    CheckCircle2,
    XCircle,
    Code2,
    FolderOpen,
    BookOpen,
    Loader2,
} from 'lucide-react';

// ── Data hooks ─────────────────────────────────────────────────────

function usePlugins() {
    return useQuery({
        queryKey: ['plugins'],
        queryFn: async () => {
            const { data } = await api.get('/plugins/');
            return data as Plugin[];
        },
    });
}

function usePluginSettings(pluginId: string) {
    return useQuery({
        queryKey: ['plugin-settings', pluginId],
        queryFn: async () => {
            const { data } = await api.get(`/plugins/${pluginId}/settings`);
            return data as { plugin_id: string; settings: PluginSettingValue[] };
        },
        enabled: !!pluginId,
    });
}

function useTogglePlugin() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
            const { data } = await api.put(`/plugins/${pluginId}/toggle`, { enabled });
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['plugins'] }),
    });
}

function useSavePluginSettings() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ pluginId, settings }: { pluginId: string; settings: { key: string; value: string | null }[] }) => {
            const { data } = await api.put(`/plugins/${pluginId}/settings`, { settings });
            return data;
        },
        onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ['plugin-settings', vars.pluginId] }),
    });
}

// ── Types ──────────────────────────────────────────────────────────

interface Plugin {
    id: string;
    slug: string;
    name: string;
    version: string;
    author: string;
    description: string;
    enabled: boolean;
    has_routes: boolean;
    has_event_listeners: boolean;
    has_widgets: boolean;
    has_nav_items: boolean;
    widgets: any[];
    nav_items: any[];
    settings_schema: PluginSettingSchema[];
    error: string | null;
}

interface PluginSettingSchema {
    key: string;
    label: string;
    type: string;
    required?: boolean;
    default?: string;
    description?: string;
}

interface PluginSettingValue extends PluginSettingSchema {
    value: string | null;
    has_value: boolean;
}

// ── Main component ────────────────────────────────────────────────

export function PluginManagement() {
    const { data: plugins = [], isLoading } = usePlugins();
    const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null);

    if (isLoading) {
        return (
            <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <Plug className="h-5 w-5 text-emerald-400" />
                    Plugin Manager
                </h2>
                <p className="text-sm text-slate-400 mt-1">
                    Manage installed plugins, configure settings, and extend platform functionality.
                </p>
            </div>

            {/* Stats */}
            <div className="grid gap-4 md:grid-cols-3">
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium text-slate-300">Installed</CardTitle>
                        <Plug className="h-4 w-4 text-emerald-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-white">{plugins.length}</div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium text-slate-300">Active</CardTitle>
                        <CheckCircle2 className="h-4 w-4 text-green-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-white">
                            {plugins.filter(p => p.enabled && !p.error).length}
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium text-slate-300">Errors</CardTitle>
                        <AlertTriangle className="h-4 w-4 text-red-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-white">
                            {plugins.filter(p => p.error).length}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Plugin List */}
            {plugins.length === 0 ? (
                <Card className="border-slate-800 bg-slate-900/50">
                    <CardContent className="py-12 text-center">
                        <FolderOpen className="h-12 w-12 text-slate-600 mx-auto mb-4" />
                        <h3 className="text-lg font-semibold text-slate-300 mb-2">
                            No plugins installed
                        </h3>
                        <p className="text-sm text-slate-500 max-w-md mx-auto">
                            Drop a plugin folder into <code className="text-emerald-400 bg-slate-800 px-1.5 py-0.5 rounded text-xs">backend/plugins/</code> and restart the server to get started.
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <div className="space-y-3">
                    {plugins.map(plugin => (
                        <PluginCard
                            key={plugin.id}
                            plugin={plugin}
                            isExpanded={expandedPlugin === plugin.id}
                            onToggleExpand={() => setExpandedPlugin(
                                expandedPlugin === plugin.id ? null : plugin.id
                            )}
                        />
                    ))}
                </div>
            )}

            {/* Developer Guide */}
            <DeveloperGuide />
        </div>
    );
}


// ── Plugin Card ───────────────────────────────────────────────────

function PluginCard({ plugin, isExpanded, onToggleExpand }: {
    plugin: Plugin;
    isExpanded: boolean;
    onToggleExpand: () => void;
}) {
    const toggle = useTogglePlugin();

    const handleToggle = async (enabled: boolean) => {
        try {
            await toggle.mutateAsync({ pluginId: plugin.id, enabled });
            toast.success(`${plugin.name} ${enabled ? 'enabled' : 'disabled'}`);
        } catch {
            toast.error('Failed to toggle plugin');
        }
    };

    return (
        <Card className="border-slate-800 bg-slate-900/50 transition-colors hover:border-slate-700">
            <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                        <div className={`p-2 rounded-lg ${plugin.error ? 'bg-red-500/10' : plugin.enabled ? 'bg-emerald-500/10' : 'bg-slate-800'}`}>
                            <Plug className={`h-5 w-5 ${plugin.error ? 'text-red-400' : plugin.enabled ? 'text-emerald-400' : 'text-slate-500'}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                                <CardTitle className="text-white text-base">{plugin.name}</CardTitle>
                                <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-500">
                                    v{plugin.version}
                                </Badge>
                                {plugin.error ? (
                                    <Badge className="bg-red-500/10 text-red-400 border-red-500/20 text-[10px]">
                                        Error
                                    </Badge>
                                ) : plugin.enabled ? (
                                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 text-[10px]">
                                        Active
                                    </Badge>
                                ) : (
                                    <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-500">
                                        Disabled
                                    </Badge>
                                )}
                            </div>
                            <CardDescription className="text-slate-400 text-sm mt-1">
                                {plugin.description}
                            </CardDescription>
                            {plugin.author && (
                                <span className="text-[11px] text-slate-600 mt-1 block">
                                    by {plugin.author}
                                </span>
                            )}

                            {/* Capability badges */}
                            <div className="flex items-center gap-2 mt-2 flex-wrap">
                                {plugin.has_routes && (
                                    <Badge variant="outline" className="text-[10px] border-blue-500/20 text-blue-400 gap-1">
                                        <Globe className="h-2.5 w-2.5" /> Routes
                                    </Badge>
                                )}
                                {plugin.has_event_listeners && (
                                    <Badge variant="outline" className="text-[10px] border-amber-500/20 text-amber-400 gap-1">
                                        <Zap className="h-2.5 w-2.5" /> Events
                                    </Badge>
                                )}
                                {plugin.has_widgets && (
                                    <Badge variant="outline" className="text-[10px] border-primary/20 text-primary gap-1">
                                        <LayoutGrid className="h-2.5 w-2.5" /> Widgets
                                    </Badge>
                                )}
                                {plugin.has_nav_items && (
                                    <Badge variant="outline" className="text-[10px] border-cyan-500/20 text-cyan-400 gap-1">
                                        <Navigation className="h-2.5 w-2.5" /> Nav
                                    </Badge>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 ml-4">
                        {plugin.settings_schema.length > 0 && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={onToggleExpand}
                                className="text-slate-400 hover:text-white h-8 gap-1"
                            >
                                <Settings className="h-3.5 w-3.5" />
                                {isExpanded ? 'Hide' : 'Settings'}
                            </Button>
                        )}
                        <Switch
                            checked={plugin.enabled}
                            onCheckedChange={handleToggle}
                            disabled={toggle.isPending}
                        />
                    </div>
                </div>

                {plugin.error && (
                    <div className="mt-3 p-3 rounded-lg bg-red-500/5 border border-red-500/20">
                        <p className="text-xs text-red-400 font-mono">{plugin.error}</p>
                    </div>
                )}
            </CardHeader>

            {/* Settings panel */}
            {isExpanded && plugin.settings_schema.length > 0 && (
                <CardContent className="border-t border-slate-800 pt-4">
                    <PluginSettingsForm pluginId={plugin.id} />
                </CardContent>
            )}
        </Card>
    );
}


// ── Settings Form ─────────────────────────────────────────────────

function PluginSettingsForm({ pluginId }: { pluginId: string }) {
    const { data, isLoading } = usePluginSettings(pluginId);
    const saveSettings = useSavePluginSettings();
    const [values, setValues] = useState<Record<string, string>>({});
    const [initialized, setInitialized] = useState(false);

    // Initialize form values from server
    if (data && !initialized) {
        const initial: Record<string, string> = {};
        for (const s of data.settings) {
            initial[s.key] = s.value ?? s.default ?? '';
        }
        setValues(initial);
        setInitialized(true);
    }

    if (isLoading) {
        return <Loader2 className="h-5 w-5 animate-spin text-slate-400 mx-auto" />;
    }

    if (!data) return null;

    const handleSave = async () => {
        try {
            await saveSettings.mutateAsync({
                pluginId,
                settings: Object.entries(values).map(([key, value]) => ({ key, value })),
            });
            toast.success('Settings saved');
        } catch {
            toast.error('Failed to save settings');
        }
    };

    return (
        <div className="space-y-4">
            <h4 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                <Settings className="h-4 w-4 text-slate-400" />
                Plugin Settings
            </h4>
            {data.settings.map(setting => (
                <div key={setting.key} className="space-y-1.5">
                    <Label className="text-sm text-slate-300 flex items-center gap-2">
                        {setting.label}
                        {setting.required && <span className="text-red-400 text-xs">*</span>}
                    </Label>
                    {setting.description && (
                        <p className="text-[11px] text-slate-500">{setting.description}</p>
                    )}
                    {setting.type === 'boolean' ? (
                        <Switch
                            checked={values[setting.key] === 'true'}
                            onCheckedChange={(checked) =>
                                setValues({ ...values, [setting.key]: String(checked) })
                            }
                        />
                    ) : (
                        <Input
                            type={setting.type === 'secret' ? 'password' : setting.type === 'number' ? 'number' : 'text'}
                            value={values[setting.key] ?? ''}
                            onChange={(e) =>
                                setValues({ ...values, [setting.key]: e.target.value })
                            }
                            placeholder={setting.default || `Enter ${setting.label}...`}
                            className="bg-slate-800 border-slate-700 text-white max-w-lg"
                        />
                    )}
                </div>
            ))}
            <Button
                onClick={handleSave}
                disabled={saveSettings.isPending}
                className="bg-emerald-600 hover:bg-emerald-700 text-white gap-2"
                size="sm"
            >
                {saveSettings.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                    <Save className="h-4 w-4" />
                )}
                Save Settings
            </Button>
        </div>
    );
}


// ── Developer Guide ───────────────────────────────────────────────

function DeveloperGuide() {
    const [open, setOpen] = useState(false);

    return (
        <Card className="border-slate-800 bg-slate-900/50">
            <CardHeader className="cursor-pointer" onClick={() => setOpen(!open)}>
                <CardTitle className="text-white text-base flex items-center gap-2">
                    <BookOpen className="h-5 w-5 text-blue-400" />
                    Plugin Developer Guide
                    <Badge variant="outline" className="text-[10px] border-blue-500/20 text-blue-400 ml-auto">
                        {open ? 'Hide' : 'Show'}
                    </Badge>
                </CardTitle>
                <CardDescription>
                    Learn how to build and install plugins for this RedWire instance.
                </CardDescription>
            </CardHeader>
            {open && (
                <CardContent className="border-t border-slate-800 pt-4 space-y-6">
                    {/* Getting Started */}
                    <div>
                        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                            <Code2 className="h-4 w-4 text-emerald-400" />
                            Getting Started
                        </h3>
                        <p className="text-sm text-slate-400 mb-3">
                            Plugins are Python packages that live in <code className="text-emerald-400 bg-slate-800 px-1.5 py-0.5 rounded text-xs">backend/plugins/</code>.
                            Each plugin is a folder containing a manifest and Python code.
                        </p>
                        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                            <pre className="text-xs text-slate-300 font-mono leading-relaxed">{`plugins/
└── my_plugin/
    ├── plugin.yaml          # Required: metadata + settings schema
    ├── __init__.py           # Required: setup() entry point
    └── router.py             # Optional: FastAPI API routes`}</pre>
                        </div>
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* Manifest */}
                    <div>
                        <h3 className="text-sm font-semibold text-white mb-2">
                            plugin.yaml — Manifest
                        </h3>
                        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                            <pre className="text-xs text-slate-300 font-mono leading-relaxed">{`name: my-plugin
version: 1.0.0
author: "Your Name"
description: "What your plugin does"

provides:
  routes: true          # Adds API endpoints
  event_listeners: true # Reacts to platform events

settings:
  - key: API_KEY
    label: "API Key"
    type: secret         # secret | string | boolean | number
    required: true
    description: "Your service API key"

widgets:
  - id: "my-widget"
    name: "My Widget"
    widget_type: "stat_card"
    data_source: "plugin:my_plugin:data"

nav_items:
  - label: "My Plugin"
    icon: "Globe"                # Any name from lib/plugin-icons.tsx; falls back to Plug
    path: "/plugins/my-plugin"
    required_permissions:        # Optional — hide from users without these
      - "engagement_view"

# Optional plugin-wide gate. Applied to every route mounted by
# this plugin AND inherited by any nav_item that doesn't declare its
# own required_permissions.
required_permissions:
  - "engagement_view"`}</pre>
                        </div>
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* Entry Point */}
                    <div>
                        <h3 className="text-sm font-semibold text-white mb-2">
                            __init__.py — Entry Point
                        </h3>
                        <p className="text-sm text-slate-400 mb-3">
                            The <code className="text-emerald-400 bg-slate-800 px-1.5 py-0.5 rounded text-xs">setup()</code> function
                            is called once at startup. Use it to register event handlers.
                        </p>
                        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                            <pre className="text-xs text-slate-300 font-mono leading-relaxed">{`def setup(app, event_bus, db_factory, manifest):
    """Called on startup. Register handlers here."""

    async def on_asset_created(event):
        print(f"New asset: {event['resource_name']}")
        # event contains: type, resource_id, resource_name,
        #   resource_type, action, engagement_id, user_id, details

    event_bus.register(
        "asset.created",
        on_asset_created,
        plugin_id=manifest.id
    )`}</pre>
                        </div>
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* Events */}
                    <div>
                        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                            <Zap className="h-4 w-4 text-amber-400" />
                            Available Events
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                            {[
                                'asset.created', 'asset.updated',
                                'finding.created', 'finding.updated',
                                'engagement.created', 'engagement.updated',
                                'testcase.created', 'testcase.updated',
                                'note.created', 'note.updated',
                                'vault.created', 'vault.updated',
                            ].map(event => (
                                <code key={event} className="text-[11px] text-amber-400 bg-amber-500/5 border border-amber-500/10 px-2 py-1 rounded font-mono">
                                    {event}
                                </code>
                            ))}
                        </div>
                        <p className="text-[11px] text-slate-500 mt-2">
                            Use wildcards: <code className="text-amber-400">asset.*</code> matches all asset events.
                            Use <code className="text-amber-400">*</code> to match everything.
                        </p>
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* API Routes */}
                    <div>
                        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                            <Globe className="h-4 w-4 text-blue-400" />
                            API Routes
                        </h3>
                        <p className="text-sm text-slate-400 mb-3">
                            Create a <code className="text-emerald-400 bg-slate-800 px-1.5 py-0.5 rounded text-xs">router.py</code> with
                            a FastAPI <code className="text-emerald-400 bg-slate-800 px-1.5 py-0.5 rounded text-xs">router</code> instance.
                            Routes are auto-mounted at <code className="text-blue-400 bg-slate-800 px-1.5 py-0.5 rounded text-xs">/plugins/your-plugin-slug/</code>.
                        </p>
                        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                            <pre className="text-xs text-slate-300 font-mono leading-relaxed">{`from fastapi import APIRouter, Depends
from auth.dependencies import get_current_user

router = APIRouter()

@router.get("/data")
async def get_data(user = Depends(get_current_user)):
    return {"message": "Hello from my plugin!"}`}</pre>
                        </div>
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* Settings Access */}
                    <div>
                        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                            <Settings className="h-4 w-4 text-slate-400" />
                            Accessing Settings
                        </h3>
                        <p className="text-sm text-slate-400 mb-3">
                            Read your plugin's settings from the database at runtime:
                        </p>
                        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                            <pre className="text-xs text-slate-300 font-mono leading-relaxed">{`from sqlalchemy import select
from models.plugin import PluginSetting

async def get_my_setting(db_factory, key):
    async with db_factory() as db:
        result = await db.execute(
            select(PluginSetting).where(
                PluginSetting.plugin_id == "my_plugin",
                PluginSetting.key == key,
            )
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else None`}</pre>
                        </div>
                    </div>
                </CardContent>
            )}
        </Card>
    );
}
