import type { Metadata } from 'next';

import './globals.css';
import NextAuthProvider from '@/providers';

export const metadata: Metadata = {
    title: 'CineVault',
    description: 'Cinematic movie discovery with AI-guided recommendations and fluid motion.',
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <body suppressHydrationWarning className="antialiased">
                <a href="#main-content" className="skip-to-content">
                    Skip to content
                </a>
                <NextAuthProvider>
                    <div id="main-content">
                        {children}
                    </div>
                </NextAuthProvider>
            </body>
        </html>
    );
}
