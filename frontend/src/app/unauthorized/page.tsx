/**
 * unauthorized/page.tsx — Permission Denied Page
 *
 * Static error page shown when a user navigates to a resource they
 * lack permissions for. Displays a "Permission Denied" card with
 * options to return to the dashboard or go back.
 */
'use client';

import { useRouter } from 'next/navigation';
import { ShieldAlert, Home, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';

export default function UnauthorizedPage() {
    const router = useRouter();

    return (
        <div className="flex min-h-screen items-center justify-center bg-linear-to-br from-slate-900 via-red-900/20 to-slate-900">
            <div className="w-full max-w-md px-4">
                <Card className="border-red-500/20 bg-slate-800/50 backdrop-blur-xs shadow-2xl">
                    <CardHeader className="space-y-1 text-center">
                        <div className="flex justify-center mb-6">
                            <div className="rounded-full bg-red-500/10 p-4 ring-1 ring-red-500/50 animate-pulse">
                                <ShieldAlert className="h-12 w-12 text-red-500" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-bold text-white">Permission Denied</CardTitle>
                        <CardDescription className="text-slate-300">
                            You do not have the necessary permissions to access this resource.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="text-center space-y-4">
                        <p className="text-sm text-slate-400">
                            If you believe this is an error, please contact your team lead or system administrator to request access.
                        </p>
                    </CardContent>
                    <CardFooter className="flex flex-col space-y-3">
                        <Button
                            className="w-full bg-red-600 hover:bg-red-700 text-white border-none shadow-lg shadow-red-900/20"
                            onClick={() => router.push('/dashboard')}
                        >
                            <Home className="mr-2 h-4 w-4" />
                            Return to Dashboard
                        </Button>
                        <Button
                            variant="ghost"
                            className="w-full text-slate-400 hover:text-white hover:bg-slate-700/50"
                            onClick={() => router.back()}
                        >
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Go Back
                        </Button>
                    </CardFooter>
                </Card>
            </div>
        </div>
    );
}
