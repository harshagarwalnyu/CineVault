'use client';

import { Movie } from '@/api';
import MovieCard from './MovieCard';

interface MovieRowProps {
    eyebrow?: string;
    title: string;
    description?: string;
    movies: Movie[];
    showRank?: boolean;
}

export default function MovieRow({
    eyebrow,
    title,
    description,
    movies,
    showRank = false,
}: MovieRowProps) {
    if (!movies || movies.length === 0) return null;

    return (
        <section className="space-y-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div className="max-w-2xl">
                    {eyebrow ? (
                        <div className="eyebrow mb-2">{eyebrow}</div>
                    ) : null}
                    <h2 className="text-3xl font-semibold text-[#f8f1e5] md:text-4xl">
                        {title}
                    </h2>
                    {description ? (
                        <p className="mt-3 text-sm leading-relaxed text-[#c0b39b] md:text-base">
                            {description}
                        </p>
                    ) : null}
                </div>
                <div className="hidden text-sm uppercase tracking-[0.22em] text-[#7f7667] lg:block">
                    Drag or scroll
                </div>
            </div>
            <div className="flex gap-5 overflow-x-auto pb-4 pr-8">
                {movies.map((movie, idx) => (
                    <MovieCard
                        key={movie.id}
                        movie={movie}
                        rank={showRank ? idx + 1 : undefined}
                        className="w-[220px] shrink-0 sm:w-[240px]"
                    />
                ))}
            </div>
        </section>
    );
}
