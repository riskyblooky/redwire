'use client';

import { useState, useEffect } from 'react';
import { useAiSettings, useUpdateAiSettings, useFetchAiModels } from '@/lib/hooks/use-admin';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Brain, Key, Globe, Cpu, RefreshCw, Save, CheckCircle2, AlertTriangle, Sparkles, MessageCircle, Unplug, ShieldOff, Plus, X, Layers, Clock, Link2, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';

export function AiSettingsManagement() {
    const { data: settings, isLoading } = useAiSettings();
    const updateSettings = useUpdateAiSettings();
    const fetchModels = useFetchAiModels();

    // API config state
    const [apiUrl, setApiUrl] = useState('https://api.openai.com/v1');
    const [apiKey, setApiKey] = useState('');
    const [tlsVerify, setTlsVerify] = useState(true);
    const [customHeaders, setCustomHeaders] = useState<{ name: string; value: string }[]>([]);
    const [extraQuery, setExtraQuery] = useState<{ name: string; value: string }[]>([]);
    const [requestTimeout, setRequestTimeout] = useState('');
    const [streamingOn, setStreamingOn] = useState(true);
    const [model, setModel] = useState('');
    const [availableModels, setAvailableModels] = useState<string[]>([]);
    const [apiHasChanges, setApiHasChanges] = useState(false);

    // Feature toggles
    const [editorEnabled, setEditorEnabled] = useState(false);
    const [chatbotEnabled, setChatbotEnabled] = useState(false);
    const [mcpEnabled, setMcpEnabled] = useState(false);
    const [writeToolsEnabled, setWriteToolsEnabled] = useState(false);

    // GHSA-f4j9-gvm9-frjw follow-up: token-budget compaction settings.
    // The backend reads these on each /ai/chat call and slides a
    // summarization window across the oldest turns when the
    // conversation pushes over threshold_pct% of max_context_tokens.
    const [maxContextTokens, setMaxContextTokens] = useState('8000');
    const [keepRecentTurns, setKeepRecentTurns] = useState('4');
    const [compactThresholdPct, setCompactThresholdPct] = useState('75');
    const [compactionHasChanges, setCompactionHasChanges] = useState(false);


    useEffect(() => {
        if (settings) {
            setApiUrl(settings.ai_api_url || 'https://api.openai.com/v1');
            setTlsVerify(settings.ai_tls_verify !== 'false');
            // Custom headers stored as a JSON object string. Parse into a
            // list to render one row per header. Anything malformed falls
            // back to an empty list so the editor still opens.
            try {
                const parsed = settings.ai_custom_headers ? JSON.parse(settings.ai_custom_headers) : {};
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    setCustomHeaders(
                        Object.entries(parsed).map(([name, value]) => ({
                            name,
                            value: String(value ?? ''),
                        }))
                    );
                } else {
                    setCustomHeaders([]);
                }
            } catch {
                setCustomHeaders([]);
            }
            try {
                const parsedQ = settings.ai_extra_query ? JSON.parse(settings.ai_extra_query) : {};
                if (parsedQ && typeof parsedQ === 'object' && !Array.isArray(parsedQ)) {
                    setExtraQuery(
                        Object.entries(parsedQ).map(([name, value]) => ({
                            name,
                            value: String(value ?? ''),
                        }))
                    );
                } else {
                    setExtraQuery([]);
                }
            } catch {
                setExtraQuery([]);
            }
            setRequestTimeout(settings.ai_request_timeout_seconds || '');
            setStreamingOn(settings.ai_streaming_enabled !== 'false');
            setModel(settings.ai_default_model || '');
            setEditorEnabled(settings.ai_enabled === 'true');
            setChatbotEnabled(settings.chatbot_enabled === 'true');
            setMcpEnabled(settings.mcp_enabled === 'true');
            setWriteToolsEnabled(settings.ai_write_tools_enabled === 'true');

            setMaxContextTokens(settings.ai_max_context_tokens || '8000');
            setKeepRecentTurns(settings.ai_compact_keep_recent_turns || '4');
            setCompactThresholdPct(settings.ai_compact_threshold_pct || '75');

            if (!apiKey) {
                setApiKey(settings.ai_api_key || '');
            }
        }
    }, [settings]);

    const handleSaveCompaction = async () => {
        try {
            await updateSettings.mutateAsync({
                ai_max_context_tokens: maxContextTokens,
                ai_compact_keep_recent_turns: keepRecentTurns,
                ai_compact_threshold_pct: compactThresholdPct,
            });
            toast.success('Compaction settings saved');
            setCompactionHasChanges(false);
        } catch {
            toast.error('Failed to save compaction settings');
        }
    };

    // ── Save: API config ────────────────────────────────────────────────
    const handleSaveApiConfig = async () => {
        try {
            // Serialise the custom headers back to a JSON object string.
            // Empty rows are dropped so an accidental "Add header" click
            // doesn't persist an empty entry. Duplicate names collapse to
            // the last value — mirrors how the backend merge treats them.
            const headerObj: Record<string, string> = {};
            for (const row of customHeaders) {
                const name = (row.name ?? '').trim();
                const value = row.value ?? '';
                if (name) headerObj[name] = value;
            }
            const queryObj: Record<string, string> = {};
            for (const row of extraQuery) {
                const name = (row.name ?? '').trim();
                const value = row.value ?? '';
                if (name) queryObj[name] = value;
            }
            const payload: Record<string, string> = {
                ai_api_url: apiUrl,
                ai_default_model: model,
                ai_tls_verify: tlsVerify ? 'true' : 'false',
                ai_custom_headers: Object.keys(headerObj).length ? JSON.stringify(headerObj) : '',
                ai_extra_query: Object.keys(queryObj).length ? JSON.stringify(queryObj) : '',
                ai_request_timeout_seconds: requestTimeout.trim(),
                ai_streaming_enabled: streamingOn ? 'true' : 'false',
            };
            if (apiKey && !apiKey.includes('...') && !apiKey.includes('***')) {
                payload.ai_api_key = apiKey;
            }
            await updateSettings.mutateAsync(payload);
            toast.success('API configuration saved');
            setApiHasChanges(false);
        } catch {
            toast.error('Failed to save API settings');
        }
    };

    // ── Save: Feature toggle (instant) ──────────────────────────────────
    const toggleFeature = async (key: string, value: boolean, label: string) => {
        try {
            await updateSettings.mutateAsync({ [key]: value ? 'true' : 'false' });
            toast.success(`${label} ${value ? 'enabled' : 'disabled'}`);
        } catch {
            toast.error(`Failed to update ${label}`);
        }
    };



    const handleFetchModels = async () => {
        try {
            const result = await fetchModels.mutateAsync();
            setAvailableModels(result.models);
            toast.success(`Found ${result.models.length} model(s)`);
        } catch (error: any) {
            toast.error(apiErrorMessage(error, 'Failed to fetch models'));
        }
    };

    const markApiChanged = () => setApiHasChanges(true);

    if (isLoading) {
        return (
            <Card className="border-slate-800 bg-slate-900/50">
                <CardContent className="p-8">
                    <p className="text-slate-400 text-center">Loading AI settings...</p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">

            {/* ═══════════════════════════════════════════════════════════
                SECTION 1: API Configuration
            ═══════════════════════════════════════════════════════════ */}
            <Card className="border-slate-800 bg-slate-900/50">
                <CardHeader>
                    <CardTitle className="text-white text-base flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
                            <Globe className="h-4 w-4 text-blue-400" />
                        </div>
                        API Configuration
                    </CardTitle>
                    <CardDescription>
                        Connect to any OpenAI-compatible API (OpenAI, Ollama, LM Studio, vLLM, etc.)
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                    {/* API URL */}
                    <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-1.5">
                            <Globe className="h-3.5 w-3.5 text-blue-400" />
                            API Base URL
                        </Label>
                        <Input
                            value={apiUrl}
                            onChange={(e) => { setApiUrl(e.target.value); markApiChanged(); }}
                            placeholder="https://api.openai.com/v1"
                            className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500 font-mono text-sm"
                        />
                        <p className="text-[11px] text-slate-500">
                            e.g. <code className="text-violet-400/70">https://api.openai.com/v1</code> or <code className="text-violet-400/70">http://host.docker.internal:11434/v1</code> for Ollama
                        </p>
                    </div>

                    {/* API Key */}
                    <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-1.5">
                            <Key className="h-3.5 w-3.5 text-amber-400" />
                            API Key
                        </Label>
                        <Input
                            type="password"
                            value={apiKey}
                            onChange={(e) => { setApiKey(e.target.value); markApiChanged(); }}
                            placeholder="sk-..."
                            className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500 font-mono text-sm"
                        />
                        <p className="text-[11px] text-slate-500">
                            Stored securely. Leave empty for local APIs that don't require authentication. JWTs and other long-form bearer tokens (up to 8 KB) are fine here.
                        </p>
                    </div>

                    {/* TLS verification toggle — mirrors ldap_tls_verify */}
                    <div className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2.5">
                        <div className="flex items-center gap-2 min-w-0">
                            <ShieldOff className={`h-3.5 w-3.5 shrink-0 ${tlsVerify ? 'text-slate-500' : 'text-amber-400'}`} />
                            <div className="min-w-0">
                                <Label className="text-slate-300 text-sm cursor-pointer" htmlFor="ai-tls-verify">
                                    Verify TLS certificate
                                </Label>
                                <p className="text-[11px] text-slate-500">
                                    Off = accept any TLS cert on the API endpoint (self-signed or private CA).
                                    Same as the LDAP toggle. Leave on unless you know why you're turning it off.
                                </p>
                            </div>
                        </div>
                        <Switch
                            id="ai-tls-verify"
                            checked={tlsVerify}
                            onCheckedChange={(v) => { setTlsVerify(v); markApiChanged(); }}
                        />
                    </div>

                    {/* Custom headers */}
                    <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-1.5">
                            <Layers className="h-3.5 w-3.5 text-emerald-400" />
                            Custom headers
                        </Label>
                        <p className="text-[11px] text-slate-500 -mt-1">
                            Sent on every request to the AI API. Common uses: <code className="text-violet-400/70">X-API-Key</code> for Anthropic-style auth, <code className="text-violet-400/70">api-version</code> for Azure, tenant / project IDs for internal proxies. Custom names override the built-in <code className="text-violet-400/70">Authorization: Bearer &lt;key&gt;</code>.
                        </p>
                        <div className="space-y-1.5">
                            {customHeaders.map((row, idx) => (
                                <div key={idx} className="flex items-center gap-2">
                                    <Input
                                        value={row.name}
                                        onChange={(e) => {
                                            const copy = [...customHeaders];
                                            copy[idx] = { ...copy[idx], name: e.target.value };
                                            setCustomHeaders(copy);
                                            markApiChanged();
                                        }}
                                        placeholder="Header-Name"
                                        className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-600 font-mono text-xs h-9 flex-1"
                                    />
                                    <Input
                                        value={row.value}
                                        onChange={(e) => {
                                            const copy = [...customHeaders];
                                            copy[idx] = { ...copy[idx], value: e.target.value };
                                            setCustomHeaders(copy);
                                            markApiChanged();
                                        }}
                                        placeholder="value"
                                        className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-600 font-mono text-xs h-9 flex-[2]"
                                    />
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => {
                                            setCustomHeaders(customHeaders.filter((_, i) => i !== idx));
                                            markApiChanged();
                                        }}
                                        className="h-9 w-9 text-slate-500 hover:text-red-400 hover:bg-red-500/10 shrink-0"
                                        aria-label="Remove header"
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            ))}
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                    setCustomHeaders([...customHeaders, { name: '', value: '' }]);
                                    markApiChanged();
                                }}
                                className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5 h-8"
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Add header
                            </Button>
                        </div>
                    </div>

                    {/* Extra query params */}
                    <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-1.5">
                            <Link2 className="h-3.5 w-3.5 text-cyan-400" />
                            Extra query parameters
                        </Label>
                        <p className="text-[11px] text-slate-500 -mt-1">
                            Appended to every AI-API request URL. Azure OpenAI needs <code className="text-violet-400/70">api-version=2024-06-01</code>; some proxies need a <code className="text-violet-400/70">project</code> or <code className="text-violet-400/70">tenant</code> id.
                        </p>
                        <div className="space-y-1.5">
                            {extraQuery.map((row, idx) => (
                                <div key={idx} className="flex items-center gap-2">
                                    <Input
                                        value={row.name}
                                        onChange={(e) => {
                                            const copy = [...extraQuery];
                                            copy[idx] = { ...copy[idx], name: e.target.value };
                                            setExtraQuery(copy);
                                            markApiChanged();
                                        }}
                                        placeholder="param"
                                        className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-600 font-mono text-xs h-9 flex-1"
                                    />
                                    <Input
                                        value={row.value}
                                        onChange={(e) => {
                                            const copy = [...extraQuery];
                                            copy[idx] = { ...copy[idx], value: e.target.value };
                                            setExtraQuery(copy);
                                            markApiChanged();
                                        }}
                                        placeholder="value"
                                        className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-600 font-mono text-xs h-9 flex-[2]"
                                    />
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => {
                                            setExtraQuery(extraQuery.filter((_, i) => i !== idx));
                                            markApiChanged();
                                        }}
                                        className="h-9 w-9 text-slate-500 hover:text-red-400 hover:bg-red-500/10 shrink-0"
                                        aria-label="Remove query param"
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            ))}
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                    setExtraQuery([...extraQuery, { name: '', value: '' }]);
                                    markApiChanged();
                                }}
                                className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5 h-8"
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Add parameter
                            </Button>
                        </div>
                    </div>

                    {/* Request timeout + streaming toggle */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <Label className="text-slate-300 flex items-center gap-1.5" htmlFor="ai-request-timeout">
                                <Clock className="h-3.5 w-3.5 text-orange-400" />
                                Request timeout (seconds)
                            </Label>
                            <Input
                                id="ai-request-timeout"
                                type="number"
                                min={5}
                                max={600}
                                value={requestTimeout}
                                onChange={(e) => { setRequestTimeout(e.target.value); markApiChanged(); }}
                                placeholder="120"
                                className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500 font-mono text-sm h-9"
                            />
                            <p className="text-[11px] text-slate-500">
                                Empty = default 120s. Bump higher for slow local models (Ollama on CPU can want 300–600). Bounded [5, 600].
                            </p>
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-slate-300 flex items-center gap-1.5">
                                <Zap className={`h-3.5 w-3.5 ${streamingOn ? 'text-yellow-400' : 'text-slate-500'}`} />
                                Streaming response
                            </Label>
                            <div className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 px-3 h-9">
                                <span className="text-xs text-slate-400">
                                    {streamingOn ? 'On (SSE)' : 'Off (buffered)'}
                                </span>
                                <Switch
                                    checked={streamingOn}
                                    onCheckedChange={(v) => { setStreamingOn(v); markApiChanged(); }}
                                />
                            </div>
                            <p className="text-[11px] text-slate-500">
                                Turn off if a proxy strips <code className="text-violet-400/70">text/event-stream</code>; the chat replies land as one buffered block.
                            </p>
                        </div>
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* Model Selection */}
                    <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-1.5">
                            <Cpu className="h-3.5 w-3.5 text-cyan-400" />
                            Default Model
                        </Label>
                        <div className="flex gap-2">
                            {availableModels.length > 0 ? (
                                <Select value={model} onValueChange={(v) => { setModel(v); markApiChanged(); }}>
                                    <SelectTrigger className="bg-slate-950 border-slate-700 text-white flex-1">
                                        <SelectValue placeholder="Select a model..." />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-950 border-slate-800 max-h-[300px]">
                                        {availableModels.map((m) => (
                                            <SelectItem key={m} value={m} className="text-slate-200 focus:bg-slate-800 focus:text-white">
                                                {m}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            ) : (
                                <Input
                                    value={model}
                                    onChange={(e) => { setModel(e.target.value); markApiChanged(); }}
                                    placeholder="gpt-4o, llama3, etc."
                                    className="bg-slate-950 border-slate-700 text-white placeholder:text-slate-500 font-mono text-sm flex-1"
                                />
                            )}
                            <Button
                                variant="outline"
                                onClick={handleFetchModels}
                                disabled={fetchModels.isPending || !apiUrl}
                                className="border-slate-700 text-slate-300 hover:bg-slate-800 gap-1.5 shrink-0"
                            >
                                <RefreshCw className={`h-3.5 w-3.5 ${fetchModels.isPending ? 'animate-spin' : ''}`} />
                                Fetch Models
                            </Button>
                        </div>
                        {availableModels.length > 0 && (
                            <p className="text-[11px] text-slate-500">
                                {availableModels.length} model(s) available.{' '}
                                <button
                                    className="text-violet-400 hover:underline"
                                    onClick={() => setAvailableModels([])}
                                >
                                    Switch to manual entry
                                </button>
                            </p>
                        )}
                    </div>

                    <Separator className="bg-slate-800" />

                    {/* Save */}
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm">
                            {apiHasChanges ? (
                                <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20 gap-1">
                                    <AlertTriangle className="h-3 w-3" /> Unsaved changes
                                </Badge>
                            ) : (
                                <Badge className="bg-green-500/10 text-green-400 border-green-500/20 gap-1">
                                    <CheckCircle2 className="h-3 w-3" /> Saved
                                </Badge>
                            )}
                        </div>
                        <Button
                            onClick={handleSaveApiConfig}
                            disabled={updateSettings.isPending || !apiHasChanges}
                            className="bg-blue-600 hover:bg-blue-500 text-white gap-1.5"
                        >
                            <Save className="h-3.5 w-3.5" />
                            Save API Config
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* ═══════════════════════════════════════════════════════════
                SECTION 2: Feature Toggles
            ═══════════════════════════════════════════════════════════ */}
            <Card className="border-slate-800 bg-slate-900/50">
                <CardHeader>
                    <CardTitle className="text-white text-base flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20">
                            <Brain className="h-4 w-4 text-violet-400" />
                        </div>
                        AI Features
                    </CardTitle>
                    <CardDescription>
                        Enable or disable individual AI-powered features. Changes take effect immediately.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-0">
                    {/* Editor AI Assistant */}
                    <div className="flex items-center justify-between py-4 border-b border-slate-800/60">
                        <div className="flex items-center gap-3">
                            <div className="p-1.5 rounded-lg bg-violet-500/10">
                                <Sparkles className="h-4 w-4 text-violet-400" />
                            </div>
                            <div>
                                <p className="text-sm font-medium text-white">Editor AI Assistant</p>
                                <p className="text-xs text-slate-500">AI assistant bar appears in all rich text editor fields</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <Badge className={editorEnabled
                                ? "bg-green-500/10 text-green-400 border-green-500/20 text-[10px]"
                                : "bg-slate-500/10 text-slate-500 border-slate-500/20 text-[10px]"
                            }>
                                {editorEnabled ? 'On' : 'Off'}
                            </Badge>
                            <Switch
                                checked={editorEnabled}
                                onCheckedChange={(v) => {
                                    setEditorEnabled(v);
                                    toggleFeature('ai_enabled', v, 'Editor AI');
                                }}
                            />
                        </div>
                    </div>

                    {/* Chatbot */}
                    <div className="flex items-center justify-between py-4 border-b border-slate-800/60">
                        <div className="flex items-center gap-3">
                            <div className="p-1.5 rounded-lg bg-emerald-500/10">
                                <MessageCircle className="h-4 w-4 text-emerald-400" />
                            </div>
                            <div>
                                <p className="text-sm font-medium text-white">Site-Wide Chatbot</p>
                                <p className="text-xs text-slate-500">Floating AI chatbot accessible from every page</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <Badge className={chatbotEnabled
                                ? "bg-green-500/10 text-green-400 border-green-500/20 text-[10px]"
                                : "bg-slate-500/10 text-slate-500 border-slate-500/20 text-[10px]"
                            }>
                                {chatbotEnabled ? 'On' : 'Off'}
                            </Badge>
                            <Switch
                                checked={chatbotEnabled}
                                onCheckedChange={(v) => {
                                    setChatbotEnabled(v);
                                    toggleFeature('chatbot_enabled', v, 'Chatbot');
                                }}
                            />
                        </div>
                    </div>

                    {/* MCP Server */}
                    <div className="flex items-center justify-between py-4">
                        <div className="flex items-center gap-3">
                            <div className="p-1.5 rounded-lg bg-cyan-500/10">
                                <Unplug className="h-4 w-4 text-cyan-400" />
                            </div>
                            <div>
                                <p className="text-sm font-medium text-white">RedWire MCP Server</p>
                                <p className="text-xs text-slate-500">Allow AI to query RedWire data (engagements, findings, assets)</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <Badge className={mcpEnabled
                                ? "bg-green-500/10 text-green-400 border-green-500/20 text-[10px]"
                                : "bg-slate-500/10 text-slate-500 border-slate-500/20 text-[10px]"
                            }>
                                {mcpEnabled ? 'On' : 'Off'}
                            </Badge>
                            <Switch
                                checked={mcpEnabled}
                                onCheckedChange={(v) => {
                                    setMcpEnabled(v);
                                    toggleFeature('mcp_enabled', v, 'MCP Server');
                                }}
                            />
                        </div>
                    </div>

                    {/* MCP Write Tools (GHSA-q4x9-5gmc-fxh5) */}
                    <div className="border-t border-slate-800 pt-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-1.5 rounded-lg bg-amber-500/10">
                                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-white">MCP Write Tools</p>
                                    <p className="text-xs text-slate-500">Allow the assistant to <span className="text-amber-300">create / update / delete</span> records via MCP</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <Badge className={writeToolsEnabled
                                    ? "bg-amber-500/10 text-amber-300 border-amber-500/20 text-[10px]"
                                    : "bg-slate-500/10 text-slate-500 border-slate-500/20 text-[10px]"
                                }>
                                    {writeToolsEnabled ? 'On' : 'Off'}
                                </Badge>
                                <Switch
                                    checked={writeToolsEnabled}
                                    onCheckedChange={(v) => {
                                        setWriteToolsEnabled(v);
                                        toggleFeature('ai_write_tools_enabled', v, 'MCP Write Tools');
                                    }}
                                />
                            </div>
                        </div>
                        <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/5 p-3">
                            <div className="flex items-start gap-2 text-xs text-red-200/90">
                                <AlertTriangle className="h-4 w-4 text-red-400 mt-0.5 shrink-0" />
                                <div className="space-y-1">
                                    <p className="font-medium text-red-200">Indirect prompt-injection risk</p>
                                    <p>
                                        A malicious string in a finding description, note, or asset name can drive the assistant
                                        to call write tools <span className="font-medium">on behalf of any user who opens it</span>.
                                        With this toggle on, writes execute autonomously. Per-call user confirmation is tracked separately
                                        and is not yet shipped — keep this off in shared or multi-tenant deployments, and only enable
                                        it on instances where every user authoring finding/note content is trusted.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>


            {/* Context-budget compaction */}
            {/* GHSA-f4j9-gvm9-frjw follow-up: token budget + sliding-
                window summarization. The defaults work well for
                gpt-4o / Claude 3.x; bump max_context_tokens for
                higher-context models, drop it for tighter ones. */}
            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                <CardHeader>
                    <CardTitle className="text-white flex items-center gap-2 text-lg">
                        <Brain className="h-5 w-5 text-violet-400" />
                        Context budget & compaction
                    </CardTitle>
                    <CardDescription>
                        Bound the size of every AI chat request — older turns are
                        summarized into a short note before the conversation pushes
                        over the token budget. Reduces cost and bounds the prompt-injection
                        blast radius of any single tool result.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-xs">Max context tokens</Label>
                            <Input
                                type="number"
                                min="1000"
                                max="200000"
                                value={maxContextTokens}
                                onChange={(e) => { setMaxContextTokens(e.target.value); setCompactionHasChanges(true); }}
                                className="bg-slate-950/50 border-slate-700 text-white font-mono"
                            />
                            <p className="text-[11px] text-slate-500">
                                Per-request budget. Suggested: 8000 for most models, 32000+ for high-context variants.
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-xs">Keep last N turns</Label>
                            <Input
                                type="number"
                                min="1"
                                max="20"
                                value={keepRecentTurns}
                                onChange={(e) => { setKeepRecentTurns(e.target.value); setCompactionHasChanges(true); }}
                                className="bg-slate-950/50 border-slate-700 text-white font-mono"
                            />
                            <p className="text-[11px] text-slate-500">
                                Recent user/assistant pairs always preserved exactly. Higher = less likely to feel forgetful.
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-slate-300 text-xs">Compact at (% of budget)</Label>
                            <Input
                                type="number"
                                min="10"
                                max="95"
                                value={compactThresholdPct}
                                onChange={(e) => { setCompactThresholdPct(e.target.value); setCompactionHasChanges(true); }}
                                className="bg-slate-950/50 border-slate-700 text-white font-mono"
                            />
                            <p className="text-[11px] text-slate-500">
                                Trigger threshold. 75% leaves headroom for the model's response.
                            </p>
                        </div>
                    </div>
                    {compactionHasChanges && (
                        <div className="flex items-center justify-end gap-2">
                            <Button
                                onClick={handleSaveCompaction}
                                className="bg-violet-600 hover:bg-violet-500 text-white"
                            >
                                <Save className="h-4 w-4 mr-1.5" /> Save compaction settings
                            </Button>
                        </div>
                    )}
                </CardContent>
            </Card>


            {/* Info footer */}
            <Card className="border-slate-800 bg-slate-900/30">
                <CardContent className="p-4">
                    <div className="flex items-start gap-3 text-sm">
                        <Sparkles className="h-4 w-4 text-violet-400 mt-0.5 shrink-0" />
                        <div className="text-slate-400 space-y-1">
                            <p>All AI features require a configured API endpoint above. API requests are proxied through the server — keys are never exposed to the browser.</p>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
