'use client';

import { useEffect } from 'react';

/**
 * Global keyboard shortcuts for power users.
 * "/" focuses the first visible search input (GitHub, YouTube, Slack pattern).
 * "Escape" blurs the active element.
 * (Don't Make Me Think: reduce friction for repeat actions)
 */
export default function KeyboardShortcuts() {
    useEffect(() => {
        const handler = (event: KeyboardEvent) => {
            const target = event.target as HTMLElement;
            const isInputFocused =
                target.tagName === 'INPUT' ||
                target.tagName === 'TEXTAREA' ||
                target.tagName === 'SELECT' ||
                target.isContentEditable;

            // "/" to focus search — only when not already in an input
            if (event.key === '/' && !isInputFocused) {
                event.preventDefault();
                const searchInput = document.querySelector<HTMLInputElement>(
                    'input[type="text"], input[placeholder*="earch"], input[placeholder*="escribe"]',
                );
                searchInput?.focus();
            }

            // Escape to blur active element
            if (event.key === 'Escape' && isInputFocused) {
                (document.activeElement as HTMLElement)?.blur();
            }
        };

        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    return null;
}
