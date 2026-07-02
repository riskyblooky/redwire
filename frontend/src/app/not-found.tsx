import Link from 'next/link';

// Skip static prerender — works around a Next 15.5.x quirk where the
// prerender step tries to render a pages-router internal /_error and
// fails with "<Html> should not be imported outside of pages/_document".
export const dynamic = 'force-dynamic';

export default function NotFound() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100 px-4">
            <div className="max-w-md text-center space-y-4">
                <div className="text-6xl font-mono font-bold text-slate-500">404</div>
                <h1 className="text-xl font-semibold">Page not found</h1>
                <p className="text-slate-400 text-sm">
                    The page you&apos;re looking for doesn&apos;t exist or has moved.
                </p>
                <div>
                    <Link
                        href="/"
                        className="inline-block rounded-md bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 text-sm font-medium transition-colors"
                    >
                        Go home
                    </Link>
                </div>
            </div>
        </div>
    );
}
