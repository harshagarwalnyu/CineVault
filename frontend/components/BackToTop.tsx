'use client';

import { useEffect, useState } from 'react';
import { m as motion, AnimatePresence } from 'framer-motion';
import { ChevronUp } from 'lucide-react';

/**
 * Floating back-to-top button that appears after scrolling past a threshold.
 * Large 48x48 tap target satisfies Fitts's Law (Laws of UX).
 * Positioned bottom-right to avoid conflicts with the AgentChat button.
 */
export default function BackToTop() {
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        const onScroll = () => setVisible(window.scrollY > 600);
        window.addEventListener('scroll', onScroll, { passive: true });
        return () => window.removeEventListener('scroll', onScroll);
    }, []);

    const scrollToTop = () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    return (
        <AnimatePresence>
            {visible && (
                <motion.button
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ type: 'spring', stiffness: 300, damping: 24 }}
                    onClick={scrollToTop}
                    className="fixed bottom-6 right-20 z-50 flex h-12 w-12 items-center justify-center rounded-full border border-white/12 bg-[rgba(12,12,14,0.84)] text-[#f2c14f] shadow-xl backdrop-blur-xl transition-colors hover:border-[#f2c14f]/35 hover:bg-white/10"
                    aria-label="Scroll to top"
                    title="Back to top"
                >
                    <ChevronUp className="h-5 w-5" />
                </motion.button>
            )}
        </AnimatePresence>
    );
}
