'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { ShieldAlert, ArrowLeft, Lock } from 'lucide-react';
import { Button } from './button';
import { Card, CardContent } from './card';

interface AccessDeniedProps {
    title?: string;
    message?: string;
    backPath?: string;
}

export const AccessDenied: React.FC<AccessDeniedProps> = ({
    title = "Access Denied",
    message = "You don't have the required permissions to view this resource.",
    backPath = "/engagements"
}) => {
    const router = useRouter();

    return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center animate-in fade-in slide-in-from-bottom-4 duration-700">
            <div className="relative mb-8">
                <div className="absolute inset-0 bg-red-500/20 blur-3xl rounded-full scale-150 animate-pulse" />
                <div className="relative bg-slate-900 border border-red-500/30 p-8 rounded-3xl shadow-2xl shadow-red-500/10 backdrop-blur-xs">
                    <ShieldAlert className="h-16 w-16 text-red-500 mx-auto" />
                </div>
            </div>

            <h1 className="text-4xl font-black text-white tracking-tighter mb-4 uppercase italic">
                {title}
            </h1>

            <p className="text-slate-400 max-w-md mx-auto mb-8 font-medium leading-relaxed">
                {message}
                <br />
                <span className="text-sm opacity-50 block mt-2 font-normal italic">
                    If you believe this is an error, please contact your team lead or system administrator.
                </span>
            </p>

            <div className="flex flex-col sm:flex-row gap-4 items-center">
                <Button
                    variant="outline"
                    onClick={() => router.push(backPath)}
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-800 text-slate-300 rounded-xl px-8"
                >
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back to Safety
                </Button>

                <Button
                    className="bg-red-600 hover:bg-red-500 text-white rounded-xl px-8 shadow-lg shadow-red-600/20"
                    onClick={() => window.location.reload()}
                >
                    <Lock className="h-4 w-4 mr-2" />
                    Re-verify Identity
                </Button>
            </div>

            <div className="mt-12 pt-8 border-t border-slate-800/50 w-full max-w-xs opacity-50">
                <div className="flex items-center justify-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                    <div className="h-1 w-1 rounded-full bg-red-500" />
                    Security Guard Active
                    <div className="h-1 w-1 rounded-full bg-red-500" />
                </div>
            </div>
        </div>
    );
};
