'use client';

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
    type ReactNode,
} from 'react';
import { m as motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

import { cn } from '@/utils';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
    id: string;
    message: string;
    type: ToastType;
    duration: number;
}

interface ToastContextValue {
    toast: (message: string, type?: ToastType, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error('useToast must be used within ToastProvider');
    return ctx;
}

const ICON_MAP: Record<ToastType, typeof Info> = {
    success: CheckCircle2,
    error: AlertCircle,
    info: Info,
};

const COLOR_MAP: Record<ToastType, string> = {
    success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    error: 'border-red-500/30 bg-red-500/10 text-red-300',
    info: 'border-[#f2c14f]/30 bg-[#f2c14f]/10 text-[#f2c14f]',
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
    const Icon = ICON_MAP[toast.type];
    const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

    useEffect(() => {
        timerRef.current = setTimeout(() => onDismiss(toast.id), toast.duration);
        return () => clearTimeout(timerRef.current);
    }, [toast.id, toast.duration, onDismiss]);

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: 24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 350, damping: 30 }}
            className={cn(
                'pointer-events-auto flex items-center gap-3 rounded-2xl border px-5 py-3.5 shadow-xl backdrop-blur-xl',
                COLOR_MAP[toast.type],
            )}
            role="alert"
            aria-live="polite"
        >
            <Icon className="h-5 w-5 shrink-0" />
            <span className="text-sm font-medium text-[#f8f1e5]">{toast.message}</span>
            <button
                onClick={() => onDismiss(toast.id)}
                className="ml-2 shrink-0 rounded-full p-1 transition hover:bg-white/10"
                aria-label="Dismiss notification"
            >
                <X className="h-3.5 w-3.5 text-[#c0b39b]" />
            </button>
        </motion.div>
    );
}

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const dismiss = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const addToast = useCallback((message: string, type: ToastType = 'info', duration = 4000) => {
        const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
        setToasts((prev) => [...prev.slice(-4), { id, message, type, duration }]);
    }, []);

    return (
        <ToastContext.Provider value={{ toast: addToast }}>
            {children}
            <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[100] flex flex-col items-center gap-2 px-4">
                <AnimatePresence mode="popLayout">
                    {toasts.map((t) => (
                        <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
                    ))}
                </AnimatePresence>
            </div>
        </ToastContext.Provider>
    );
}
