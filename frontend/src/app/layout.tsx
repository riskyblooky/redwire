/**
 * layout.tsx — Root Layout
 *
 * Top-level layout wrapping all pages. Configures the Inter font,
 * dark mode class, global CSS, favicon, and <Providers> (React Query,
 * Zustand auth hydration, Toaster, etc.).
 */
import './globals.css';
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import { Providers } from './providers';

const inter = Inter({ subsets: ['latin'], display: 'swap', preload: false });

export const metadata: Metadata = {
    title: 'RedWire - Red Team Operations Platform',
    description: 'Secure platform for red team reporting and operations management',
    icons: {
        icon: '/r.png',
    },
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en" className="dark">
            <body className={inter.className}>
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}
