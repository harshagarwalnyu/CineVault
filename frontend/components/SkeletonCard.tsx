'use client';

import { cn } from '@/utils';

/**
 * Skeleton loading card that mirrors the MovieCard layout.
 * Uses CSS shimmer animation for perceived performance.
 * (Refactoring UI: empty states should mirror final layout)
 */

function Shimmer({ className }: { className?: string }) {
    return (
        <div
            className={cn(
                'animate-shimmer rounded-lg bg-gradient-to-r from-white/[0.03] via-white/[0.08] via-50% to-white/[0.03] bg-[length:200%_100%]',
                className,
            )}
        />
    );
}

export function SkeletonCard({ className }: { className?: string }) {
    return (
        <div className={cn('poster-card', className)}>
            <div className="relative aspect-[2/3] overflow-hidden rounded-[1.75rem] bg-white/[0.02]">
                {/* Full card shimmer background */}
                <Shimmer className="absolute inset-0 !rounded-[1.75rem]" />

                {/* Top badges */}
                <div className="absolute inset-x-0 top-0 flex items-start justify-between p-4">
                    <Shimmer className="h-6 w-16 rounded-full" />
                </div>

                {/* Bottom content area */}
                <div className="absolute inset-x-0 bottom-0 space-y-3 p-4">
                    <Shimmer className="h-3 w-20 rounded-full" />
                    <div className="space-y-2">
                        <Shimmer className="h-5 w-3/4 rounded-lg" />
                        <Shimmer className="h-5 w-1/2 rounded-lg" />
                    </div>
                    <div className="flex gap-2">
                        <Shimmer className="h-6 w-16 rounded-full" />
                        <Shimmer className="h-6 w-14 rounded-full" />
                    </div>
                </div>
            </div>
        </div>
    );
}

export function SkeletonGrid({
    count = 8,
    className,
}: {
    count?: number;
    className?: string;
}) {
    return (
        <div
            className={cn(
                'grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5',
                className,
            )}
        >
            {Array.from({ length: count }).map((_, i) => (
                <SkeletonCard key={i} />
            ))}
        </div>
    );
}

export function SkeletonRow({ className }: { className?: string }) {
    return (
        <div className={cn('space-y-5', className)}>
            <div className="space-y-2">
                <Shimmer className="h-3 w-28 rounded-full" />
                <Shimmer className="h-8 w-64 rounded-lg" />
            </div>
            <div className="flex gap-4 overflow-hidden">
                {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="w-[200px] shrink-0">
                        <SkeletonCard />
                    </div>
                ))}
            </div>
        </div>
    );
}
