'use client';

import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Loader2, Mail, Send, CheckCircle2 } from 'lucide-react';

interface SmtpConfig {
    enabled: boolean;
    host: string;
    port: number;
    username: string;
    password: string;
    from_email: string;
    from_name: string;
    use_tls: boolean;
}

const DEFAULT_CONFIG: SmtpConfig = {
    enabled: false,
    host: '',
    port: 587,
    username: '',
    password: '',
    from_email: '',
    from_name: 'RedWire',
    use_tls: true,
};

export default function EmailSettings() {
    const [config, setConfig] = useState<SmtpConfig>(DEFAULT_CONFIG);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testEmail, setTestEmail] = useState('');
    const [testing, setTesting] = useState(false);
    const [dirty, setDirty] = useState(false);

    useEffect(() => {
        api.get('/admin/auth-settings/smtp')
            .then(({ data }) => {
                if (data.smtp) {
                    setConfig({
                        ...DEFAULT_CONFIG,
                        ...data.smtp,
                        password: data.smtp.password === '••••••••' ? '' : data.smtp.password || '',
                    });
                }
            })
            .catch(() => toast.error('Failed to load email settings'))
            .finally(() => setLoading(false));
    }, []);

    const handleChange = (key: keyof SmtpConfig, value: string | number | boolean) => {
        setConfig(prev => ({ ...prev, [key]: value }));
        setDirty(true);
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const payload = { ...config };
            // Don't send empty password (keeps existing)
            if (!payload.password) {
                payload.password = null as any;
            }
            await api.put('/admin/auth-settings/smtp', payload);
            toast.success('Email settings saved');
            setDirty(false);
        } catch (e: any) {
            toast.error(e.response?.data?.detail || 'Failed to save email settings');
        } finally {
            setSaving(false);
        }
    };

    const handleTest = async () => {
        if (!testEmail) {
            toast.error('Enter a test email address');
            return;
        }
        setTesting(true);
        try {
            const { data } = await api.post('/admin/auth-settings/smtp/test', { to_email: testEmail });
            if (data.success) {
                toast.success(data.message);
            } else {
                toast.error(data.message);
            }
        } catch (e: any) {
            toast.error(e.response?.data?.detail || 'Failed to send test email');
        } finally {
            setTesting(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
        );
    }

    const inputClass = "w-full px-3 py-2 text-sm bg-slate-900/50 border border-slate-700/50 rounded-lg text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30 transition-colors";
    const labelClass = "block text-xs font-medium text-slate-400 mb-1.5";

    return (
        <div className="space-y-6 max-w-2xl">
            <Card className="bg-slate-900/40 border-slate-700/50">
                <CardHeader>
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-indigo-500/10 rounded-lg">
                            <Mail className="h-5 w-5 text-indigo-400" />
                        </div>
                        <div>
                            <CardTitle className="text-lg text-slate-100">SMTP Configuration</CardTitle>
                            <CardDescription>Configure email delivery for notifications and password resets</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="space-y-5">
                    {/* Enabled toggle */}
                    <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/30">
                        <div>
                            <p className="text-sm font-medium text-slate-200">Enable Email</p>
                            <p className="text-xs text-slate-500">Allow the system to send emails</p>
                        </div>
                        <Switch
                            checked={config.enabled}
                            onCheckedChange={(v) => handleChange('enabled', v)}
                        />
                    </div>

                    {/* Server settings */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className={labelClass}>SMTP Host</label>
                            <input
                                className={inputClass}
                                placeholder="smtp.gmail.com"
                                value={config.host}
                                onChange={(e) => handleChange('host', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className={labelClass}>Port</label>
                            <input
                                className={inputClass}
                                type="number"
                                placeholder="587"
                                value={config.port}
                                onChange={(e) => handleChange('port', parseInt(e.target.value) || 587)}
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className={labelClass}>Username</label>
                            <input
                                className={inputClass}
                                placeholder="user@example.com"
                                value={config.username}
                                onChange={(e) => handleChange('username', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className={labelClass}>Password</label>
                            <input
                                className={inputClass}
                                type="password"
                                placeholder="••••••••"
                                value={config.password}
                                onChange={(e) => handleChange('password', e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className={labelClass}>From Email</label>
                            <input
                                className={inputClass}
                                placeholder="noreply@company.com"
                                value={config.from_email}
                                onChange={(e) => handleChange('from_email', e.target.value)}
                            />
                        </div>
                        <div>
                            <label className={labelClass}>From Name</label>
                            <input
                                className={inputClass}
                                placeholder="RedWire"
                                value={config.from_name}
                                onChange={(e) => handleChange('from_name', e.target.value)}
                            />
                        </div>
                    </div>

                    {/* TLS toggle */}
                    <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg border border-slate-700/30">
                        <div>
                            <p className="text-sm font-medium text-slate-200">Use TLS</p>
                            <p className="text-xs text-slate-500">Enable STARTTLS encryption (recommended)</p>
                        </div>
                        <Switch
                            checked={config.use_tls}
                            onCheckedChange={(v) => handleChange('use_tls', v)}
                        />
                    </div>

                    {/* Save button */}
                    <Button
                        onClick={handleSave}
                        disabled={saving || !dirty}
                        className="w-full bg-primary hover:bg-primary/90 text-white"
                    >
                        {saving ? (
                            <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Saving...</>
                        ) : (
                            <><CheckCircle2 className="h-4 w-4 mr-2" /> Save Email Settings</>
                        )}
                    </Button>
                </CardContent>
            </Card>

            {/* Test email */}
            <Card className="bg-slate-900/40 border-slate-700/50">
                <CardHeader>
                    <CardTitle className="text-base text-slate-100">Send Test Email</CardTitle>
                    <CardDescription>Verify your SMTP configuration by sending a test email</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-3">
                        <input
                            className={inputClass + " flex-1"}
                            placeholder="test@example.com"
                            value={testEmail}
                            onChange={(e) => setTestEmail(e.target.value)}
                        />
                        <Button
                            onClick={handleTest}
                            disabled={testing || !testEmail}
                            variant="outline"
                            className="border-slate-700 hover:bg-slate-800"
                        >
                            {testing ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <><Send className="h-4 w-4 mr-2" /> Send Test</>
                            )}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500 mt-2">
                        Make sure to save your settings before sending a test email.
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
