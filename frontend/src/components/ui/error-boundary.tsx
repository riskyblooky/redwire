'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

/**
 * Error Boundary that catches rendering errors in any child component tree
 * and shows a recovery UI instead of crashing the entire page.
 */
export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('[ErrorBoundary] Caught error:', error, errorInfo);
    }

    handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
                    <div className="flex flex-col items-center gap-4 max-w-md text-center">
                        <div className="p-4 rounded-full bg-red-500/10 border border-red-500/20">
                            <AlertTriangle className="h-8 w-8 text-red-400" />
                        </div>
                        <h2 className="text-xl font-semibold text-white">Something went wrong</h2>
                        <p className="text-sm text-slate-400">
                            An unexpected error occurred while rendering this section.
                            Try refreshing or navigating back.
                        </p>
                        {this.state.error && (
                            <pre className="mt-2 max-w-full overflow-x-auto rounded-lg bg-slate-900/50 border border-slate-800 p-3 text-xs text-red-300 font-mono">
                                {this.state.error.message}
                            </pre>
                        )}
                        <div className="flex gap-3 mt-2">
                            <Button
                                variant="outline"
                                onClick={this.handleReset}
                                className="border-slate-700 text-slate-300 hover:bg-slate-800"
                            >
                                <RefreshCw className="h-4 w-4 mr-2" />
                                Try Again
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => window.location.reload()}
                                className="border-slate-700 text-slate-300 hover:bg-slate-800"
                            >
                                Reload Page
                            </Button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
