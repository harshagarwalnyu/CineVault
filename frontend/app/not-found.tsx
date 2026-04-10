import Link from 'next/link';
import { Clapperboard, Home, Search } from 'lucide-react';

/**
 * Custom 404 page with clear recovery paths.
 * (Don't Make Me Think: never leave users at a dead end)
 * (Refactoring UI: empty states need illustration + CTA)
 */
export default function NotFound() {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-bg)] px-4 text-center text-[var(--color-foreground)]">
            <div className="mx-auto max-w-lg">
                <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full border border-[#f2c14f]/25 bg-[#f2c14f]/8">
                    <Clapperboard className="h-9 w-9 text-[#f2c14f]" />
                </div>

                <h1 className="mt-8 text-6xl font-bold tracking-tight text-[#f8f1e5] sm:text-8xl">
                    404
                </h1>
                <p className="mt-4 text-lg text-[#c0b39b]">
                    This scene was cut from the final edit.
                </p>
                <p className="mt-2 text-sm text-[#b9ab94]">
                    The page you were looking for doesn&apos;t exist or has been moved.
                </p>

                <div className="mt-10 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
                    <Link
                        href="/"
                        className="button-primary inline-flex items-center gap-2 px-6 py-3 text-sm"
                    >
                        <Home className="h-4 w-4" />
                        Back to Home
                    </Link>
                    <Link
                        href="/search"
                        className="button-secondary inline-flex items-center gap-2 px-6 py-3 text-sm"
                    >
                        <Search className="h-4 w-4" />
                        Search Catalog
                    </Link>
                </div>
            </div>
        </main>
    );
}
