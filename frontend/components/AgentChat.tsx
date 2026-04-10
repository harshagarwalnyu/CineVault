'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, m as motion, useReducedMotion } from 'framer-motion';
import { Bot, Send, Sparkles, X } from 'lucide-react';

import { ChatMessage, movieApi } from '@/api';

export default function AgentChat() {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState<ChatMessage[]>([
        {
            role: 'assistant',
            content: 'Tell me the mood, tempo, or kind of ending you want. I’ll pull together a sharper movie shortlist.',
        },
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const prefersReducedMotion = useReducedMotion();

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMessage = input;
        setInput('');
        setMessages((previous) => [...previous, { role: 'user', content: userMessage }]);
        setIsLoading(true);

        try {
            const history = messages.map((message) => ({
                role: message.role,
                content: message.content,
            }));
            const response = await movieApi.chat(userMessage, history);

            setMessages((previous) => [
                ...previous,
                {
                    role: 'assistant',
                    content: response.response,
                },
            ]);
        } catch (error) {
            console.error(error);
            setMessages((previous) => [
                ...previous,
                {
                    role: 'assistant',
                    content: 'The concierge link stalled. Try again in a second and I’ll rerun the search.',
                },
            ]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div id="ai-concierge" className="fixed bottom-5 right-5 z-50 sm:bottom-7 sm:right-7">
            <AnimatePresence initial={false}>
                {!isOpen ? (
                    <motion.button
                        key="concierge-trigger"
                        initial={prefersReducedMotion ? false : { opacity: 0, y: 22 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
                        transition={{ duration: 0.35, ease: 'easeOut' }}
                        onClick={() => setIsOpen(true)}
                        className="group flex items-center gap-3 rounded-full border border-[#f2c14f]/30 bg-[rgba(10,10,12,0.92)] px-5 py-3 text-[#f8f1e5] shadow-[0_18px_45px_rgba(0,0,0,0.28)] backdrop-blur-xl transition hover:border-[#f2c14f]/55"
                    >
                        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#f2c14f]/12 text-[#f2c14f]">
                            <Bot size={20} />
                        </div>
                        <div className="text-left">
                            <div className="text-[0.68rem] uppercase tracking-[0.3em] text-[#c0b39b]">
                                Concierge
                            </div>
                            <div className="font-semibold">Need a sharper pick?</div>
                        </div>
                    </motion.button>
                ) : (
                    <motion.div
                        key="concierge-panel"
                        initial={prefersReducedMotion ? false : { opacity: 0, y: 26, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 20, scale: 0.98 }}
                        transition={{ duration: 0.26, ease: 'easeOut' }}
                        className="flex h-[560px] w-[min(92vw,410px)] flex-col overflow-hidden rounded-[2rem] border border-white/10 bg-[rgba(11,11,14,0.94)] shadow-[0_30px_90px_rgba(0,0,0,0.45)] backdrop-blur-xl"
                    >
                        <div className="flex items-center justify-between border-b border-white/[0.08] bg-[linear-gradient(120deg,rgba(242,193,79,0.16),rgba(160,71,71,0.18))] px-5 py-4 text-[#f8f1e5]">
                            <div className="flex items-center gap-3">
                                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#f2c14f]/12 text-[#f2c14f]">
                                    <Sparkles size={18} />
                                </div>
                                <div>
                                    <h3 className="font-semibold">Movie Concierge</h3>
                                    <p className="text-xs uppercase tracking-[0.24em] text-[#d8ccb8]">
                                        Describe the vibe, not just the title
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={() => setIsOpen(false)}
                                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 transition hover:border-[#f2c14f]/35"
                            >
                                <X size={18} />
                            </button>
                        </div>

                        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5" ref={scrollRef}>
                            {messages.map((message, index) => (
                                <div
                                    key={`${message.role}-${index}`}
                                    className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                                >
                                    <div
                                        className={`max-w-[88%] rounded-[1.4rem] px-4 py-3 text-sm leading-relaxed ${message.role === 'user'
                                            ? 'rounded-br-md bg-[#f2c14f] text-[#120d09]'
                                            : 'rounded-bl-md border border-white/[0.08] bg-white/[0.06] text-[#f8f1e5]'
                                            }`}
                                    >
                                        {message.content}
                                    </div>
                                </div>
                            ))}

                            {isLoading ? (
                                <div className="flex justify-start">
                                    <div className="rounded-[1.4rem] rounded-bl-md border border-white/[0.08] bg-white/[0.06] px-4 py-3 text-[#d8ccb8]">
                                        Thinking through the shortlist...
                                    </div>
                                </div>
                            ) : null}
                        </div>

                        <form onSubmit={handleSubmit} className="border-t border-white/[0.08] bg-black/20 p-4">
                            <div className="relative">
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(event) => setInput(event.target.value)}
                                    placeholder="Moody thrillers with sharp dialogue..."
                                    className="w-full rounded-full border border-white/10 bg-white/[0.06] px-4 py-3 pr-14 text-sm text-[#f8f1e5] placeholder:text-[#8b8173] focus:border-[#f2c14f]/35 focus:outline-none"
                                />
                                <button
                                    type="submit"
                                    disabled={isLoading || !input.trim()}
                                    className="absolute right-2 top-2 inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#7d1f1f] text-white transition hover:bg-[#922424] disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    <Send size={16} />
                                </button>
                            </div>
                        </form>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
