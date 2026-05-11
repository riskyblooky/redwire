'use client';

import { useState, useCallback } from 'react';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { AlertTriangle, Trash2, ShieldAlert } from 'lucide-react';

interface ConfirmDialogState {
    open: boolean;
    title: string;
    description: string;
    confirmLabel?: string;
    variant?: 'destructive' | 'warning' | 'default';
    extraAction?: { label: string; variant?: 'outline' | 'destructive' | 'default' };
    onConfirm: () => void;
    onExtra?: () => void;
}

const initialState: ConfirmDialogState = {
    open: false,
    title: '',
    description: '',
    onConfirm: () => { },
};

export function useConfirmDialog() {
    const [state, setState] = useState<ConfirmDialogState>(initialState);

    const confirm = useCallback(({
        title,
        description,
        confirmLabel,
        variant = 'destructive',
        extraAction,
    }: {
        title: string;
        description: string;
        confirmLabel?: string;
        variant?: 'destructive' | 'warning' | 'default';
        extraAction?: { label: string; variant?: 'outline' | 'destructive' | 'default' };
    }): Promise<boolean | 'extra'> => {
        return new Promise((resolve) => {
            setState({
                open: true,
                title,
                description,
                confirmLabel,
                variant,
                extraAction,
                onConfirm: () => {
                    setState(initialState);
                    resolve(true);
                },
                onExtra: extraAction ? () => {
                    setState(initialState);
                    resolve('extra');
                } : undefined,
            });
        });
    }, []);

    const handleCancel = useCallback(() => {
        setState(initialState);
    }, []);

    const ConfirmDialog = useCallback(() => {
        const variantStyles = {
            destructive: {
                icon: <Trash2 className="h-5 w-5 text-red-400" />,
                buttonClass: 'bg-red-600 hover:bg-red-700 text-white',
                defaultLabel: 'Delete',
            },
            warning: {
                icon: <AlertTriangle className="h-5 w-5 text-amber-400" />,
                buttonClass: 'bg-amber-600 hover:bg-amber-700 text-white',
                defaultLabel: 'Continue',
            },
            default: {
                icon: <ShieldAlert className="h-5 w-5 text-blue-400" />,
                buttonClass: 'bg-primary hover:bg-primary/90 text-white',
                defaultLabel: 'Confirm',
            },
        };

        const style = variantStyles[state.variant || 'destructive'];

        const extraButtonClass = state.extraAction?.variant === 'destructive'
            ? 'bg-red-600/30 hover:bg-red-600/50 text-red-300 border border-red-500/40'
            : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600';

        return (
            <AlertDialog open={state.open} onOpenChange={(open) => !open && handleCancel()}>
                <AlertDialogContent className="bg-slate-950 border-slate-800">
                    <AlertDialogHeader>
                        <AlertDialogTitle className="text-white flex items-center gap-2">
                            {style.icon}
                            {state.title}
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-slate-400">
                            {state.description}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel className="bg-slate-900 border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white">
                            Cancel
                        </AlertDialogCancel>
                        {state.extraAction && state.onExtra && (
                            <AlertDialogAction
                                onClick={state.onExtra}
                                className={extraButtonClass}
                            >
                                {state.extraAction.label}
                            </AlertDialogAction>
                        )}
                        <AlertDialogAction
                            onClick={state.onConfirm}
                            className={style.buttonClass}
                        >
                            {state.confirmLabel || style.defaultLabel}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        );
    }, [state, handleCancel]);

    return { confirm, ConfirmDialog };
}

/**
 * Extracts a user-friendly error message from API errors.
 * Specifically handles 403 permission denied errors with detailed messages.
 */
export function getErrorMessage(error: any, fallback: string): string {
    // Check for Axios-style error response
    const status = error?.response?.status;
    const detail = error?.response?.data?.detail;

    if (status === 403) {
        // Permission denied - use the backend's detail message if available
        return typeof detail === 'string' ? detail : 'You do not have permission to perform this action.';
    }

    // Handle Pydantic validation errors (detail is an array of objects)
    if (Array.isArray(detail)) {
        const first = detail[0];
        if (first?.msg) return first.msg;
        return fallback;
    }

    // For other errors, use detail if available, otherwise fallback
    return (typeof detail === 'string' ? detail : null) || error?.message || fallback;
}
