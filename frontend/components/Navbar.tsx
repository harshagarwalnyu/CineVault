'use client';

import Link from 'next/link';
import { m as motion, useMotionValueEvent, useScroll } from 'framer-motion';
import { Clapperboard, Compass, LogOut, Search, User } from 'lucide-react';
import { signIn, signOut, useSession } from 'next-auth/react';
import { useState } from 'react';

import { cn } from '@/utils';

export default function Navbar() {
    const { data: session } = useSession();
    const { scrollY, scrollYProgress } = useScroll();
    const [scrolled, setScrolled] = useState(false);

    useMotionValueEvent(scrollY, 'change', (value) => {
        setScrolled(value > 18);
    });

    return (
        <nav
            className={cn(
                'fixed inset-x-0 top-0 z-50 transition-all duration-500',
                scrolled ? 'px-3 pt-3 sm:px-6' : 'px-0 pt-0',
            )}
        >
            <div
                className={cn(
                    'mx-auto flex h-[4.5rem] max-w-[1400px] items-center justify-between border-b border-white/[0.08] px-4 sm:px-6 lg:px-8',
                    scrolled
                        ? 'rounded-full border bg-[rgba(12,12,14,0.84)] shadow-[0_24px_80px_rgba(0,0,0,0.35)] backdrop-blur-xl'
                        : 'bg-transparent',
                )}
            >
                <div className="flex items-center gap-8">
                    <Link href="/" className="group flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[#f2c14f]/30 bg-[#f2c14f]/10 text-[#f2c14f] transition group-hover:border-[#f2c14f]/55 group-hover:bg-[#f2c14f]/14">
                            <Clapperboard className="h-5 w-5" />
                        </div>
                        <div>
                            <div className="font-[family-name:var(--font-display)] text-3xl uppercase tracking-[0.16em] text-[#f8f1e5]">
                                CineVault
                            </div>
                            <div className="text-[0.65rem] uppercase tracking-[0.4em] text-[#c0b39b]">
                                Motion Picture Intelligence
                            </div>
                        </div>
                    </Link>

                    <div className="hidden items-center gap-2 lg:flex">
                        <Link href="/" className="nav-link">Home</Link>
                        <Link href="/search" className="nav-link">Search</Link>
                        <Link href="/#signals" className="nav-link">Signals</Link>
                        <Link href="/agentic" className="nav-link !text-purple-400 font-bold flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span>Agentic Mode</Link>
                        {session ? (
                            <Link href="/my-list" className="nav-link">My List</Link>
                        ) : null}
                    </div>
                </div>

                <div className="flex items-center gap-2 sm:gap-3">
                    <Link
                        href="/search"
                        className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-[#f8f1e5] transition hover:border-[#f2c14f]/35 hover:bg-white/[0.08] md:inline-flex"
                    >
                        <Search className="h-4 w-4 text-[#f2c14f]" />
                        Search
                    </Link>

                    <Link
                        href="/search"
                        className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[#f8f1e5] transition hover:border-[#f2c14f]/35 hover:bg-white/[0.08] md:hidden"
                        aria-label="Search movies"
                    >
                        <Search className="h-4 w-4" />
                    </Link>

                    {session ? (
                        <div className="flex items-center gap-3 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-[#f8f1e5]">
                            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#7d1f1f] text-white">
                                <User className="h-4 w-4" />
                            </div>
                            <div className="hidden sm:block">
                                <div className="text-xs uppercase tracking-[0.24em] text-[#c0b39b]">
                                    Profile
                                </div>
                                <div className="text-sm font-semibold">
                                    {session.user?.name || 'Collector'}
                                </div>
                            </div>
                            <button
                                onClick={() => signOut()}
                                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[#f8f1e5] transition hover:border-[#f2c14f]/35 hover:text-[#f2c14f]"
                                title="Logout"
                            >
                                <LogOut className="h-4 w-4" />
                            </button>
                        </div>
                    ) : (
                        <button
                            onClick={() => signIn()}
                            className="button-primary px-5 py-2.5 text-sm"
                        >
                            <Compass className="h-4 w-4" />
                            Sign In
                        </button>
                    )}
                </div>

                <motion.div
                    className="absolute inset-x-0 bottom-0 h-px origin-left bg-gradient-to-r from-[#f2c14f] via-[#a04747] to-transparent"
                    style={{ scaleX: scrollYProgress }}
                />
            </div>
        </nav>
    );
}
