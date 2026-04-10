'use client';

import { FormEvent, Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { signIn } from 'next-auth/react';

import Navbar from '@/components/Navbar';

function LoginPageContent() {
    const searchParams = useSearchParams();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const error = searchParams.get('error');

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setIsSubmitting(true);

        await signIn('credentials', {
            username,
            password,
            callbackUrl: '/',
        });

        setIsSubmitting(false);
    };

    return (
        <main className="min-h-screen overflow-x-hidden bg-[var(--color-bg)] text-[var(--color-foreground)]">
            <Navbar />
            <div className="page-frame grid min-h-screen items-center gap-8 pt-28 pb-16 lg:grid-cols-[1.05fr_0.95fr]">
                <section className="surface-panel p-6 sm:p-8 lg:p-10">
                    <div className="eyebrow">CineVault Access</div>
                    <h1 className="mt-3 text-4xl font-semibold text-[#f8f1e5] sm:text-5xl">
                        Enter the recommendation vault.
                    </h1>
                    <p className="mt-4 max-w-xl text-base leading-relaxed text-[#c0b39b]">
                        Sign in to unlock personalized recommendation rails, account-aware signals, and saved discovery sessions.
                    </p>

                    <div className="mt-8 grid gap-4 sm:grid-cols-2">
                        <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                            <div className="eyebrow">Sample User</div>
                            <p className="mt-3 text-sm leading-relaxed text-[#d8ccb8]">
                                If seed data exists locally, try <code>user_1</code> with <code>sample-user-1</code>.
                            </p>
                        </div>
                        <div className="rounded-[1.4rem] border border-white/[0.08] bg-black/[0.18] p-5">
                            <div className="eyebrow">After Sign-In</div>
                            <p className="mt-3 text-sm leading-relaxed text-[#d8ccb8]">
                                You’ll return to the upgraded homepage with personalized routes enabled.
                            </p>
                        </div>
                    </div>
                </section>

                <section className="surface-panel p-6 sm:p-8 lg:p-10">
                    <div className="text-sm uppercase tracking-[0.26em] text-[#c0b39b]">Credentials</div>
                    <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
                        <label className="block">
                            <span className="mb-2 block text-sm text-[#d8ccb8]">Username</span>
                            <input
                                className="w-full rounded-[1.25rem] border border-white/10 bg-black/25 px-4 py-3 text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                value={username}
                                onChange={(event) => setUsername(event.target.value)}
                                autoComplete="username"
                                required
                            />
                        </label>

                        <label className="block">
                            <span className="mb-2 block text-sm text-[#d8ccb8]">Password</span>
                            <input
                                type="password"
                                className="w-full rounded-[1.25rem] border border-white/10 bg-black/25 px-4 py-3 text-[#f8f1e5] outline-none transition focus:border-[#f2c14f]/35"
                                value={password}
                                onChange={(event) => setPassword(event.target.value)}
                                autoComplete="current-password"
                                required
                            />
                        </label>

                        {error ? (
                            <div className="rounded-[1.2rem] border border-[#8f2d2d]/50 bg-[#8f2d2d]/12 px-4 py-3 text-sm text-[#f5d2d2]">
                                Sign-in failed. Check your username and password.
                            </div>
                        ) : null}

                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="button-primary w-full px-5 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            {isSubmitting ? 'Signing in...' : 'Sign in'}
                        </button>
                    </form>

                    <div className="mt-6 text-sm text-[#b9ab94]">
                        Need to inspect the catalog first?{' '}
                        <Link href="/" className="text-[#f2c14f] hover:text-[#f6d176]">
                            Return to the homepage
                        </Link>
                        .
                    </div>
                </section>
            </div>
        </main>
    );
}

export default function LoginPage() {
    return (
        <Suspense fallback={<main className="min-h-screen bg-[var(--color-bg)] text-[var(--color-foreground)]" />}>
            <LoginPageContent />
        </Suspense>
    );
}
