"use client";

import { LazyMotion, domAnimation } from 'framer-motion';
import { SessionProvider } from "next-auth/react";
import { useEffect } from 'react';

import Lenis from 'lenis';
import { ToastProvider } from '@/components/Toast';
import BackToTop from '@/components/BackToTop';
import KeyboardShortcuts from '@/components/KeyboardShortcuts';

export default function NextAuthProvider({ children }: { children: React.ReactNode }) {
    useEffect(() => {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            return undefined;
        }

        const lenis = new Lenis({
            autoRaf: false,
            duration: 1.1,
            smoothWheel: true,
            syncTouch: false,
            wheelMultiplier: 0.95,
            touchMultiplier: 1.05,
        });

        let frame = 0;

        const raf = (time: number) => {
            lenis.raf(time);
            frame = window.requestAnimationFrame(raf);
        };

        frame = window.requestAnimationFrame(raf);

        return () => {
            window.cancelAnimationFrame(frame);
            lenis.destroy();
        };
    }, []);

    return (
        <SessionProvider>
            <LazyMotion features={domAnimation} strict>
                <ToastProvider>
                    {children}
                    <BackToTop />
                    <KeyboardShortcuts />
                </ToastProvider>
            </LazyMotion>
        </SessionProvider>
    );
}
